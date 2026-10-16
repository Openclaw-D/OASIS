#include "OasisHUD.h"
#include "OasisPawn.h"
#include "OasisWorld.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "CanvasItem.h"
#include "GameFramework/PlayerController.h"
#include "SceneView.h"

void AOasisHUD::Text(const FString& Value, FVector2D Position, float Size, FLinearColor Color)
{
    FCanvasTextItem Item(Position, FText::FromString(Value), GEngine->GetSmallFont(), Color);
    Item.Scale = FVector2D(Size / 12.0 * Scale);
    // A white outline overlaps small glyphs at Retina scale; use clean ink instead.
    Item.bOutlined = false;
    Canvas->DrawItem(Item);
}

void AOasisHUD::Button(const FString& Label, FVector2D Position, float Width, TFunction<void()> Action)
{
    const FBox2D Bounds(Position, Position + FVector2D(Width, 40 * Scale));
    const AOasisPawn* Pawn = Cast<AOasisPawn>(PlayerOwner->GetPawn());
    if (Pawn && Bounds.IsInside(Pawn->GetPointerPosition()))
        DrawRect(FLinearColor(.96f, .96f, .96f, MenuFade), Position.X - 8 * Scale, Position.Y, Width, 40 * Scale);
    Text(Label, Position + FVector2D(0, 11 * Scale), 17, FLinearColor(.035f, .035f, .035f, MenuFade));
    // Continue drawing the fade, but closed settings must not accept clicks.
    if (Pawn && Pawn->MenuOpen) Buttons.Add({Bounds, MoveTemp(Action)});
}

bool AOasisHUD::HandleClick(const FVector2D& Position)
{
    for (const auto& Item : Buttons)
        if (Item.Bounds.IsInside(Position)) { Item.Action(); return true; }
    return false;
}

void AOasisHUD::DrawGeography(AOasisPawn* Pawn)
{
    AOasisWorld* World = Pawn->GetOasisWorld();
    const double Altitude = Pawn->GetAltitude();
    if (!World) return;
    const auto Project = [this](const FVector& Point, FVector2D& Screen)
    {
        return Canvas->SceneView && Canvas->SceneView->ScreenToPixel(Canvas->SceneView->WorldToScreen(Point), Screen);
    };
    if (Altitude > 3000 && Altitude < 300000)
    {
        const float CityAlpha = FMath::Clamp((Altitude - 3000) / 5000.0, 0.0, 1.0) * FMath::Clamp((300000 - Altitude) / 120000.0, 0.0, 1.0);
        for (const auto& Path : World->GetCityPaths())
        {
            FVector2D Previous;
            bool PreviousVisible = false;
            for (const FVector& Point : Path.Positions)
            {
                FVector2D Screen;
                const bool Visible = Pawn->GetEye().Z > Point.Z && Project(Point, Screen);
                if (Visible && PreviousVisible && (Screen - Previous).Size() < Canvas->ClipX * .3 &&
                    FMath::Min(Screen.X, Previous.X) < Canvas->ClipX && FMath::Max(Screen.X, Previous.X) > 0 &&
                    FMath::Min(Screen.Y, Previous.Y) < Canvas->ClipY && FMath::Max(Screen.Y, Previous.Y) > 0)
                    DrawLine(Previous.X, Previous.Y, Screen.X, Screen.Y, FLinearColor(.55, .55, .55, CityAlpha * .55f), .7f * Scale);
                Previous = Screen;
                PreviousVisible = Visible;
            }
        }
    }
    if (Altitude < 80000) return;
    const float Alpha = FMath::Clamp((Altitude - 80000.0) / 170000.0, 0.0, 1.0);
    const FVector Eye = Pawn->GetEye();
    for (const auto& Border : World->GetBorders())
    {
        const FLinearColor Color = Border.Name == TEXT("China") ? FLinearColor(.05, .05, .05, Alpha) : FLinearColor(.28, .28, .28, Alpha * .85f);
        bool PreviousVisible = false;
        FVector2D Previous;
        for (int32 I = 0; I < Border.Positions.Num(); ++I)
        {
            const FVector& Point = Border.Positions[I];
            FVector2D Screen;
            const bool Visible = FVector::DotProduct(Border.Normals[I], Eye - Point) > 0 && Project(Point, Screen);
            if (Visible && PreviousVisible && (Screen - Previous).Size() < Canvas->ClipX * .4 &&
                FMath::Min(Screen.X, Previous.X) < Canvas->ClipX && FMath::Max(Screen.X, Previous.X) > 0 &&
                FMath::Min(Screen.Y, Previous.Y) < Canvas->ClipY && FMath::Max(Screen.Y, Previous.Y) > 0)
                DrawLine(Previous.X, Previous.Y, Screen.X, Screen.Y, Color, Pawn->LineWeight * .75f * Scale);
            Previous = Screen;
            PreviousVisible = Visible;
        }
    }
    // Graticules share the actual WGS84 globe rather than a separate map camera.
    const auto Graticule = [&](bool Latitude, double Fixed)
    {
        bool PreviousVisible = false;
        FVector2D Previous;
        for (int32 I = 0; I <= 180; ++I)
        {
            const double Varying = Latitude ? -180.0 + I * 2 : -90.0 + I;
            const FVector LLH(Latitude ? Varying : Fixed, Latitude ? Fixed : Varying, 100);
            const FVector Point = World->FromLLH(LLH);
            const FVector Normal = (World->FromLLH(LLH + FVector(0, 0, 10)) - Point).GetSafeNormal();
            FVector2D Screen;
            const bool Visible = FVector::DotProduct(Normal, Eye - Point) > 0 && Project(Point, Screen);
            if (Visible && PreviousVisible && (Screen - Previous).Size() < Canvas->ClipX * .3)
                DrawLine(Previous.X, Previous.Y, Screen.X, Screen.Y, FLinearColor(.65, .65, .65, Alpha * .32f), .65f * Scale);
            Previous = Screen;
            PreviousVisible = Visible;
        }
    };
    for (int32 Latitude = -60; Latitude <= 60; Latitude += 30) Graticule(true, Latitude);
    for (int32 Longitude = -180; Longitude < 180; Longitude += 30) Graticule(false, Longitude);
    FVector2D Anchor;
    const FVector Shanghai = World->FromLLH(FVector(121.501909, 31.2364814, 200));
    if (FVector::DotProduct((Shanghai - World->EarthCenter()).GetSafeNormal(), Eye - Shanghai) > 0 &&
        Project(Shanghai, Anchor))
    {
        constexpr int32 Segments = 36;
        for (int32 I = 0; I < Segments; ++I)
        {
            const float A = 2 * PI * I / Segments, B = 2 * PI * (I + 1) / Segments;
            DrawLine(Anchor.X + FMath::Cos(A) * 6 * Scale, Anchor.Y + FMath::Sin(A) * 6 * Scale,
                     Anchor.X + FMath::Cos(B) * 6 * Scale, Anchor.Y + FMath::Sin(B) * 6 * Scale,
                     FLinearColor(.15, .15, .15, Alpha), Scale);
        }
        if (!Pawn->HideUI) Text(TEXT("SHANGHAI"), Anchor + FVector2D(12, -7) * Scale, 12, FLinearColor(.12, .12, .12, Alpha));
    }
}

void AOasisHUD::DrawHUD()
{
    Super::DrawHUD();
    AOasisPawn* Pawn = Cast<AOasisPawn>(PlayerOwner->GetPawn());
    if (!Pawn || !Canvas || !Pawn->GetOasisWorld()) return;
    Scale = FMath::Clamp(Canvas->ClipY / 1440.f, .75f, 2.f);
    Buttons.Reset();
    DrawGeography(Pawn);
    const float Now = GetWorld()->GetRealTimeSeconds();
    const float Idle = Now - Pawn->LastInteraction;
    const float Opacity = Pawn->AutoHide && Idle > 3 ? .42f : .78f;
    if (!Pawn->HideUI)
    {
        const FVector2D Gear(Canvas->ClipX - 44 * Scale, 44 * Scale);
        const FBox2D GearBounds(Gear - FVector2D(20 * Scale), Gear + FVector2D(20 * Scale));
        const float GearAlpha = GearBounds.IsInside(Pawn->GetPointerPosition()) || Pawn->MenuOpen ? 1.f : Opacity;
        const FLinearColor Ink(.035, .035, .035, GearAlpha);
        for (int32 I = 0; I < 48; ++I)
        {
            const float A = 2 * PI * I / 48, B = 2 * PI * (I + 1) / 48;
            const float RadiusA = (I % 6 < 3 ? 10 : 8) * Scale;
            const float RadiusB = ((I + 1) % 6 < 3 ? 10 : 8) * Scale;
            DrawLine(Gear.X + FMath::Cos(A) * RadiusA, Gear.Y + FMath::Sin(A) * RadiusA,
                     Gear.X + FMath::Cos(B) * RadiusB, Gear.Y + FMath::Sin(B) * RadiusB, Ink, 1.5f * Scale);
            DrawLine(Gear.X + FMath::Cos(A) * 3 * Scale, Gear.Y + FMath::Sin(A) * 3 * Scale,
                     Gear.X + FMath::Cos(B) * 3 * Scale, Gear.Y + FMath::Sin(B) * 3 * Scale, Ink, Scale);
        }
        Buttons.Add({GearBounds, [Pawn]() { Pawn->MenuOpen = !Pawn->MenuOpen; }});
        const double Altitude = Pawn->GetAltitude();
        const FString Place = Altitude > 8000000 ? TEXT("Earth") : Altitude > 150000 ? TEXT("China") : Altitude > 5000 ? TEXT("Shanghai") : TEXT("Lujiazui");
        Text(Place, FVector2D(24 * Scale, 28 * Scale), 15, FLinearColor(.1, .1, .1, Opacity));
        if (Idle < 12)
            Text(TEXT("Drag to orbit   /   Scroll to zoom   /   Double-click to fly   /   Esc for menu"),
                 FVector2D(24 * Scale, Canvas->ClipY - 46 * Scale), 13, FLinearColor(.2, .2, .2, .55f * FMath::Clamp(12.f - Idle, 0.f, 1.f)));
    }
    MenuFade = FMath::FInterpTo(MenuFade, Pawn->MenuOpen ? 1.f : 0.f, GetWorld()->GetDeltaSeconds(), 15.f);
    if (MenuFade < .01f) return;
    DrawRect(FLinearColor(1, 1, 1, MenuFade * .72f), 0, 0, Canvas->ClipX, Canvas->ClipY);
    DrawRect(FLinearColor(1, 1, 1, MenuFade * .96f), 0, 0, 360 * Scale, Canvas->ClipY);
    DrawLine(360 * Scale, 0, 360 * Scale, Canvas->ClipY, FLinearColor(.84, .84, .84, MenuFade), Scale);
    Text(TEXT("OASIS"), FVector2D(32, 48) * Scale, 22, FLinearColor(.04, .04, .04, MenuFade));
    Text(TEXT("A shared world"), FVector2D(32, 80) * Scale, 13, FLinearColor(.4, .4, .4, MenuFade));
    float Y = 130 * Scale;
    const auto Row = [&](const FString& Label, TFunction<void()> Action)
    {
        Button(Label, FVector2D(32 * Scale, Y), 296 * Scale, MoveTemp(Action));
        Y += 40 * Scale;
    };
    Text(TEXT("PLACES"), FVector2D(32 * Scale, Y - 20 * Scale), 12, FLinearColor(.4, .4, .4, MenuFade));
    Row(TEXT("Earth"), [Pawn]() { Pawn->FlyToScale(0); Pawn->MenuOpen = false; });
    Row(TEXT("China"), [Pawn]() { Pawn->FlyToScale(1); Pawn->MenuOpen = false; });
    Row(TEXT("Shanghai"), [Pawn]() { Pawn->FlyToScale(2); Pawn->MenuOpen = false; });
    Row(TEXT("Lujiazui"), [Pawn]() { Pawn->FlyToScale(3); Pawn->MenuOpen = false; });
    Y += 44 * Scale;
    Text(TEXT("LOOK & MOTION"), FVector2D(32 * Scale, Y - 20 * Scale), 12, FLinearColor(.4, .4, .4, MenuFade));
    Row(FString::Printf(TEXT("Lines                 %.1f"), Pawn->LineWeight), [Pawn]() { Pawn->SetLineWeight(Pawn->LineWeight >= 2 ? 1 : Pawn->LineWeight + .5f); });
    Row(FString::Printf(TEXT("Render scale      %d%%"), Pawn->RenderScale), [Pawn]() { Pawn->SetRenderScale(Pawn->RenderScale == 100 ? 75 : Pawn->RenderScale == 75 ? 67 : 100); });
    Row(Pawn->AmbientEnabled ? TEXT("Ambient shading    On") : TEXT("Ambient shading    Off"), [Pawn]() { Pawn->SetAmbient(!Pawn->AmbientEnabled); });
    Row(Pawn->AutoHide ? TEXT("Auto-hide                  On") : TEXT("Auto-hide                  Off"), [Pawn]() { Pawn->SetAutoHide(!Pawn->AutoHide); });
    Y += 30 * Scale;
    Row(TEXT("Reverse flight        R"), [Pawn]() { Pawn->Reverse(); Pawn->MenuOpen = false; });
    Row(TEXT("Close                        Esc"), [Pawn]() { Pawn->MenuOpen = false; });
    Text(TEXT("1–7   Camera views\nH       Hide interface\nR       Reverse flight"), FVector2D(32 * Scale, Canvas->ClipY - 140 * Scale), 13, FLinearColor(.4, .4, .4, MenuFade));
    Text(TEXT("Source & reconstruction estimates"), FVector2D(32 * Scale, Canvas->ClipY - 52 * Scale), 11, FLinearColor(.5, .5, .5, MenuFade));
}
