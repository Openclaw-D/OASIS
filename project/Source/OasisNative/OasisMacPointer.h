#pragma once

#include "CoreMinimal.h"

// Read the position carried by this app's own mouse events, in viewport pixels.
// No system-wide event tap, cursor warping, or input synthesis is used.
#if PLATFORM_MAC
struct FOasisMacClick
{
    FVector2D Position;
    int32 Count = 1;
};
void InstallOasisMacPointer();
void RemoveOasisMacPointer();
bool ReadOasisMacPointer(FVector2D& Position, FIntPoint ViewportSize);
bool ConsumeOasisMacDrag(FVector2D& Delta, FIntPoint ViewportSize);
void ConsumeOasisMacClicks(TArray<FOasisMacClick>& Clicks, FIntPoint ViewportSize);
double ConsumeOasisMacScroll();
void DiscardOasisMacDrag();
#endif
