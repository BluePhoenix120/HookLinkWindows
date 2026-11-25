// The device's microphone for a game's audio input streams on iOS: the capture backend of audio_input.c (its platform hooks), which converts, mixes and fans the samples out to
// each open stream (hle_audio.c, nn::audio's InputStream). The Legend of Zelda: Ocarina of Time (Switch 2) plays its ocarina by voice through two such streams. DM_MIC=1 (the
// launcher's Microphone row) offers the microphone to the game; without it, or without permission or an app usage description, the host lists no input device. The Mac's backend is
// audio_input_mac.m
#pragma once
int dm_mic_wanted(void);       // DM_MIC is on
int dm_mic_available(void);    // wanted, the app may ask for the microphone (its usage description) and the user has not refused it
void dm_mic_prepare(void);     // ask for the permission early (the iOS front end's audio session setup), so the game's first listing finds it decided
