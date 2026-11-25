// The device's microphone on iOS (mic_apple.h): AVAudioEngine's input node, handed to audio_input.c as planar Float32 at the device's rate (dm_audio_input_process), which converts it
// to the game's 48 kHz mono PCM16, applies DM_MIC_GAIN and fills each open stream. HookLink X3: this backend replaces HookLink's own ring and input streams (from kid-with-sword-remake),
// now that nxnative main has the shared input layer; on the Mac audio_input_mac.m is the backend
#import "mic_apple.h"
#import <AVFAudio/AVFAudio.h>
#import <Foundation/Foundation.h>
#include <TargetConditionals.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "dm.h"
#include "audio_input.h"

int dm_mic_wanted(void) { static int v = -1; if (v < 0) { const char *e = getenv("DM_MIC"); v = e && atoi(e) != 0; } return v; }

// The app must say why it asks for the microphone: without NSMicrophoneUsageDescription the system ends a process that touches it (a test binary, an app packed without it)
static int mic_described(void) { return [NSBundle.mainBundle objectForInfoDictionaryKey:@"NSMicrophoneUsageDescription"] != nil; }

int dm_mic_available(void) {
    if (!dm_mic_wanted() || !mic_described()) return 0;
    if (@available(iOS 17.0, macOS 14.0, *)) return AVAudioApplication.sharedInstance.recordPermission != AVAudioApplicationRecordPermissionDenied;   // undecided: asked at the first start
    return 1;
}

void dm_mic_prepare(void) {
    if (!dm_mic_wanted() || !mic_described()) { if (dm_mic_wanted()) LOG("[RED] microphone: DM_MIC is on but the app has no microphone usage description: the game gets no input device"); return; }
    if (@available(iOS 17.0, macOS 14.0, *)) {
        if (AVAudioApplication.sharedInstance.recordPermission != AVAudioApplicationRecordPermissionUndetermined) {
            LOG("microphone: permission %s", AVAudioApplication.sharedInstance.recordPermission == AVAudioApplicationRecordPermissionGranted ? "granted" : "refused (Settings > Privacy > Microphone)"); return; }
        [AVAudioApplication requestRecordPermissionWithCompletionHandler:^(BOOL granted) { LOG("microphone: permission %s", granted ? "granted" : "refused"); }];
    }
}

#if TARGET_OS_IPHONE
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static AVAudioEngine *g_engine; static double g_rate; static int g_channels; static _Atomic int g_failed;

int dm_audio_input_platform_device_available(void) { return dm_mic_available(); }
int dm_audio_input_platform_prepare(void) { return dm_mic_available() ? 0 : -1; }
int dm_audio_input_platform_start(void) {
    pthread_mutex_lock(&g_mu);
    if (g_engine) { pthread_mutex_unlock(&g_mu); return 0; }
    AVAudioEngine *e = [AVAudioEngine new];
    AVAudioInputNode *in = e.inputNode;
    AVAudioFormat *hw = [in outputFormatForBus:0];
    if (!hw || hw.sampleRate <= 0 || hw.channelCount == 0 || hw.commonFormat != AVAudioPCMFormatFloat32 || hw.isInterleaved) {
        pthread_mutex_unlock(&g_mu); atomic_store(&g_failed, 1);
        LOG("[RED] microphone: no float input (the device has none, or the audio session cannot record)"); return -1; }
    double rate = hw.sampleRate; int ch = (int)hw.channelCount;
    [in installTapOnBus:0 bufferSize:1024 format:hw block:^(AVAudioPCMBuffer *buf, AVAudioTime *when) {
        (void)when;
        if (buf.frameLength && buf.floatChannelData) dm_audio_input_process((const float *const *)buf.floatChannelData, (int)buf.format.channelCount, buf.frameLength, rate);
    }];
    NSError *err = nil;
    [e prepare];
    if (![e startAndReturnError:&err]) { [in removeTapOnBus:0]; pthread_mutex_unlock(&g_mu); atomic_store(&g_failed, 1); LOG("[RED] microphone: the capture did not start: %s", err.localizedDescription.UTF8String); return -1; }
    g_engine = e; g_rate = rate; g_channels = ch; atomic_store(&g_failed, 0);
    pthread_mutex_unlock(&g_mu);
    LOG("microphone: capturing (%.0f Hz x%d, converted to 48 kHz mono by audio_input.c)", rate, ch);
    return 0;
}
void dm_audio_input_platform_close(void) {
    pthread_mutex_lock(&g_mu);
    if (g_engine) { [g_engine.inputNode removeTapOnBus:0]; [g_engine stop]; g_engine = nil; LOG("microphone: stopped"); }   // removeTap returns once the tap's block is done
    pthread_mutex_unlock(&g_mu);
}
int dm_audio_input_platform_failed(void) { return atomic_load(&g_failed); }
int dm_audio_input_platform_route_changed(void) { return 0; }   // the front end's audio session restarts the outputs; the engine follows the route itself
void dm_audio_input_platform_info(char name[0x100], char uid[0x100], double *sample_rate, int *channels) {
    if (name) snprintf(name, 0x100, "iPhone microphone"); if (uid) uid[0] = 0;
    if (sample_rate) *sample_rate = g_rate; if (channels) *channels = g_channels;
}
#endif
