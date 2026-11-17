#import <UIKit/UIKit.h>
#import "../../dm/ios/Sources/DmGameMenu.h"
void *dm_game_menu(void) {
    UIDeferredMenuElement *deferred = [UIDeferredMenuElement elementWithUncachedProvider:^(void (^done)(NSArray<UIMenuElement *> *)) {
        NSMutableArray<UIMenuElement *> *items = [NSMutableArray array];
        NSArray<NSString *> *names = @[@"2D", @"3D", @"Tap", @"Mobile"];
        for (int i = 0; i < 4; i++) {
            if (!dm_pad_layout_offered(i)) continue;
            UIAction *a = [UIAction actionWithTitle:names[i] image:nil identifier:nil handler:^(__unused UIAction *action) { dm_pad_layout_set(i); }];
            a.state = dm_pad_layout() == i ? UIMenuElementStateOn : UIMenuElementStateOff;
            [items addObject:a];
        }
        done(@[[UIMenu menuWithTitle:@"Controller layout" image:nil identifier:nil options:UIMenuOptionsSingleSelection children:items]]);
    }];
    UIMenu *menu = [UIMenu menuWithTitle:@"" children:@[deferred]];
    return (__bridge_retained void *)menu;
}
