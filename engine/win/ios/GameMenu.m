#import <UIKit/UIKit.h>
#import "../../dm/ios/Sources/DmGameMenu.h"
void *dm_game_menu(void) {
    UIDeferredMenuElement *deferred = [UIDeferredMenuElement elementWithUncachedProvider:^(void (^done)(NSArray<UIMenuElement *> *)) {
        NSMutableArray<UIMenuElement *> *items = [NSMutableArray array];
        NSArray<NSString *> *names = @[@"2D", @"3D", @"Tap", @"Mobile", @"Custom"];
        for (int i = 0; i < 5; i++) {
            if (!dm_pad_layout_offered(i)) continue;
            UIAction *a = [UIAction actionWithTitle:names[i] image:nil identifier:nil handler:^(__unused UIAction *action) { dm_pad_layout_set(i); }];
            a.state = dm_pad_layout() == i ? UIMenuElementStateOn : UIMenuElementStateOff;
            [items addObject:a];
        }
        NSMutableArray<UIMenuElement *> *rows = [NSMutableArray arrayWithObject:[UIMenu menuWithTitle:@"" image:nil identifier:nil options:UIMenuOptionsDisplayInline | UIMenuOptionsSingleSelection children:items]];
        if (dm_pad_layout() == 4 && dm_pad_layout_offered(4)) {
            [rows addObject:[UIAction actionWithTitle:@"Edit custom layout…" image:[UIImage systemImageNamed:@"hand.draw"] identifier:nil handler:^(__unused UIAction *action) { dm_pad_custom_edit(); }]];
        }
        done(@[[UIMenu menuWithTitle:@"Controller layout" children:rows]]);
    }];
    UIMenu *menu = [UIMenu menuWithTitle:@"" children:@[deferred]];
    return (__bridge_retained void *)menu;
}
