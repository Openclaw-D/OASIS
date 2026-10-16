#include "OasisMacPointer.h"

#if PLATFORM_MAC
#include "Mac/CocoaThread.h"
#include "Misc/ScopeLock.h"

namespace
{
id PointerMonitor = nil;
FCriticalSection PointerLock;
FVector2D NormalizedPointer;
FVector2D DragPrevious, PendingDrag = FVector2D::ZeroVector;
TArray<FOasisMacClick> PendingClicks;
double PendingScroll = 0;
bool HasPointer = false;
bool LeftDown = false;
}

void InstallOasisMacPointer()
{
    MainThreadCall(^{
        if (PointerMonitor) return;
        const NSEventMask Mask = NSEventMaskMouseMoved | NSEventMaskLeftMouseDown |
            NSEventMaskLeftMouseUp | NSEventMaskLeftMouseDragged | NSEventMaskScrollWheel;
        PointerMonitor = [NSEvent addLocalMonitorForEventsMatchingMask:Mask handler:^NSEvent*(NSEvent* Event) {
            NSWindow* Window = Event.window;
            if (!Window || ![Window.title hasPrefix:@"OasisNative"]) return Event;
            NSView* View = Window.contentView;
            const NSRect Bounds = View.bounds;
            if (Bounds.size.width <= 0 || Bounds.size.height <= 0) return Event;
            const NSPoint Point = [View convertPoint:Event.locationInWindow fromView:nil];
            const double Y = View.isFlipped ? Point.y - Bounds.origin.y : NSMaxY(Bounds) - Point.y;
            FScopeLock Lock(&PointerLock);
            const FVector2D NewPointer((Point.x - Bounds.origin.x) / Bounds.size.width, Y / Bounds.size.height);
            const bool InViewport = NewPointer.X >= 0 && NewPointer.X < 1 && NewPointer.Y >= 0 && NewPointer.Y < 1;
            if (Event.type == NSEventTypeLeftMouseDown)
            {
                if (!InViewport) return Event; // Preserve native title-bar/window controls.
                DragPrevious = NewPointer;
                LeftDown = true;
                PendingClicks.Add({NewPointer, FMath::Max(1, int32(Event.clickCount))});
            }
            else if (Event.type == NSEventTypeLeftMouseDragged)
            {
                if (LeftDown) PendingDrag += NewPointer - DragPrevious;
                DragPrevious = NewPointer;
                LeftDown = true;
            }
            else if (Event.type == NSEventTypeLeftMouseUp) LeftDown = false;
            else if (Event.type == NSEventTypeScrollWheel && InViewport)
            {
                // Precise trackpad deltas are measured in points; a detented
                // wheel already supplies logical steps. Keep both continuous.
                const double Steps = Event.scrollingDeltaY / (Event.hasPreciseScrollingDeltas ? 40.0 : 1.0);
                if (FMath::IsFinite(Steps)) PendingScroll += Steps;
            }
            NormalizedPointer = NewPointer;
            HasPointer = true;
            // The own Canvas viewport consumes clicks/drag below. Slate's Mac
            // cursor cache can disagree with remote NSEvent coordinates, which
            // otherwise routes a content double click to a stale window zone.
            if (InViewport && (Event.type == NSEventTypeLeftMouseDown ||
                Event.type == NSEventTypeLeftMouseUp || Event.type == NSEventTypeLeftMouseDragged ||
                Event.type == NSEventTypeScrollWheel)) return nil;
            return Event;
        }];
    });
}

void RemoveOasisMacPointer()
{
    MainThreadCall(^{
        if (PointerMonitor) [NSEvent removeMonitor:PointerMonitor];
        PointerMonitor = nil;
    });
}

bool ReadOasisMacPointer(FVector2D& Position, FIntPoint ViewportSize)
{
    FScopeLock Lock(&PointerLock);
    if (!HasPointer || ViewportSize.X <= 0 || ViewportSize.Y <= 0) return false;
    Position = NormalizedPointer * FVector2D(ViewportSize);
    return true;
}

bool ConsumeOasisMacDrag(FVector2D& Delta, FIntPoint ViewportSize)
{
    FScopeLock Lock(&PointerLock);
    Delta = PendingDrag * FVector2D(ViewportSize);
    PendingDrag = FVector2D::ZeroVector;
    return !Delta.IsNearlyZero();
}

void DiscardOasisMacDrag()
{
    FScopeLock Lock(&PointerLock);
    PendingDrag = FVector2D::ZeroVector;
    PendingClicks.Reset();
    PendingScroll = 0;
}

double ConsumeOasisMacScroll()
{
    FScopeLock Lock(&PointerLock);
    const double Steps = FMath::Clamp(PendingScroll, -8.0, 8.0);
    PendingScroll = 0;
    return Steps;
}

void ConsumeOasisMacClicks(TArray<FOasisMacClick>& Clicks, FIntPoint ViewportSize)
{
    FScopeLock Lock(&PointerLock);
    Clicks = MoveTemp(PendingClicks);
    PendingClicks.Reset();
    for (auto& Click : Clicks) Click.Position *= FVector2D(ViewportSize);
}
#endif
