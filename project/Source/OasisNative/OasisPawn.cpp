#include "OasisPawn.h"
#include "OasisWorld.h"
#include "OasisHUD.h"
#include "OasisMacPointer.h"
#include "Camera/CameraComponent.h"
#include "Components/InputComponent.h"
#include "Components/SceneComponent.h"
#include "InputCoreTypes.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ConfigCacheIni.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
FVector2D MousePosition(APlayerController* Controller)
{
    if (!Controller) return FVector2D::ZeroVector;
#if PLATFORM_MAC
    FIntPoint Size;
    Controller->GetViewportSize(Size.X, Size.Y);
    FVector2D NativePosition;
    if (ReadOasisMacPointer(NativePosition, Size)) return NativePosition;
#endif
    float X = 0, Y = 0;
    Controller->GetMousePosition(X, Y);
    return FVector2D(X, Y);
}
}

AOasisPawn::AOasisPawn()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("CameraRoot"));
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("CinematicCamera"));
    Camera->SetupAttachment(RootComponent);
    Camera->bUsePawnControlRotation = false;
    Camera->PostProcessSettings.bOverride_MotionBlurAmount = true;
    Camera->PostProcessSettings.MotionBlurAmount = 0;
    Camera->PostProcessSettings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
    Camera->PostProcessSettings.AutoExposureApplyPhysicalCameraExposure = false;
}

void AOasisPawn::BeginPlay()
{
    Super::BeginPlay();
    TActorIterator<AOasisWorld> ExistingWorld(GetWorld());
    if (ExistingWorld) World = *ExistingWorld;
    if (!World) World = GetWorld()->SpawnActor<AOasisWorld>();
    Pose = ScalePose(0);
    if (APlayerController* PC = Cast<APlayerController>(GetController()))
    {
        PC->bShowMouseCursor = true;
        FInputModeGameOnly Mode;
        Mode.SetConsumeCaptureMouseDown(false);
        PC->SetInputMode(Mode);
        if (GEngine && GEngine->GameViewport)
        {
            GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::CaptureDuringMouseDown);
            GEngine->GameViewport->SetMouseLockMode(EMouseLockMode::DoNotLock);
            GEngine->GameViewport->SetHideCursorDuringCapture(false);
        }
    }
    FConfigFile Preferences;
    Preferences.Read(FPaths::ProjectSavedDir() / TEXT("OasisPreferences.ini"));
    Preferences.GetFloat(TEXT("Look"), TEXT("LineWeight"), LineWeight);
    Preferences.GetInt(TEXT("Look"), TEXT("RenderScale"), RenderScale);
    Preferences.GetBool(TEXT("Look"), TEXT("AmbientEnabled"), AmbientEnabled);
    Preferences.GetBool(TEXT("Look"), TEXT("AutoHide"), AutoHide);
    LineWeight = FMath::Clamp(LineWeight, 1.f, 2.f);
    if (RenderScale != 100 && RenderScale != 75 && RenderScale != 67) RenderScale = 100;
    if (UGameUserSettings* Settings = UGameUserSettings::GetGameUserSettings())
    {
        // Fixed 16:9 review window, rendered with the Mac's native Retina backing.
        Settings->SetFullscreenMode(EWindowMode::Windowed);
        Settings->SetScreenResolution(FIntPoint(2880, 1620));
        Settings->SetFrameRateLimit(60);
        Settings->ApplyResolutionSettings(false);
        Settings->ApplyNonResolutionSettings();
    }
    MetricsStart = PreviousWallTime = FPlatformTime::Seconds();
    LastInteraction = GetWorld()->GetRealTimeSeconds();
    ApplyPose();
    SetLineWeight(LineWeight);
    SetRenderScale(RenderScale);
    SetAmbient(AmbientEnabled);
}

void AOasisPawn::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
#if !PLATFORM_MAC
    Input->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &AOasisPawn::PressPointer);
    Input->BindKey(EKeys::LeftMouseButton, IE_DoubleClick, this, &AOasisPawn::DoubleClickPointer);
    Input->BindKey(EKeys::LeftMouseButton, IE_Released, this, &AOasisPawn::ReleasePointer);
    Input->BindKey(EKeys::MouseScrollUp, IE_Pressed, this, &AOasisPawn::ZoomIn);
    Input->BindKey(EKeys::MouseScrollDown, IE_Pressed, this, &AOasisPawn::ZoomOut);
#endif
    Input->BindKey(EKeys::Escape, IE_Pressed, this, &AOasisPawn::ToggleMenu);
    Input->BindKey(EKeys::H, IE_Pressed, this, &AOasisPawn::ToggleUI);
    Input->BindKey(EKeys::R, IE_Pressed, this, &AOasisPawn::Reverse);
    Input->BindKey(EKeys::SpaceBar, IE_Pressed, this, &AOasisPawn::Reverse);
    const TArray<FKey> Keys = {EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six, EKeys::Seven};
    for (int32 I = 0; I < Keys.Num(); ++I)
    {
        FInputKeyBinding Binding(FInputChord(Keys[I]), IE_Pressed);
        Binding.KeyDelegate.GetDelegateForManualSet().BindLambda([this, I]() { FlyToPreset(I + 1); });
        Input->KeyBindings.Add(Binding);
    }
}

FOasisPose AOasisPawn::ScalePose(int32 Scale) const
{
    if (Scale >= 3) return PresetPose(2);
    const TArray<FVector> LLH = {FVector(104, 35, 20000000), FVector(104.2, 35.9, 5500000), FVector(121.47, 31.23, 60000)};
    FOasisPose Result;
    Result.Eye = World->FromLLH(LLH[Scale]);
    Result.Target = Scale == 0 ? World->EarthCenter() : World->FromLLH(FVector(LLH[Scale].X, LLH[Scale].Y, 0));
    return Result;
}

FOasisPose AOasisPawn::PresetPose(int32 Preset) const
{
    static const FVector Eyes[] = {{-880, 250, 40}, {-900, 900, 900}, {-880, 250, 1.7}, {0, 0, 5600}, {9.5, -166.5, 560}, {1050, -1250, 1150}, {-920, 0, 700}};
    static const FVector Targets[] = {{-38.5, -7.3, 203.1}, {0, 0, 150}, {0, -4, 215.7}, {0, 0, 0}, {56.5, 129.8, 450.8}, {0, 0, 240}, {0, 0, 320}};
    static const double Lenses[] = {21, 24, 21, 50, 24, 27, 27};
    const int32 Index = FMath::Clamp(Preset - 1, 0, 6);
    const auto ESU = [](FVector V) { return FVector(V.X, -V.Y, V.Z) * 100; };
    return {ESU(Eyes[Index]), ESU(Targets[Index]), Lenses[Index]};
}

void AOasisPawn::StartFlight(const FOasisPose& NewPose, double Duration, const FString& Label)
{
    Start = Pose;
    Destination = NewPose;
    StartLLH = World->ToLLH(Start.Eye);
    EndLLH = World->ToLLH(Destination.Eye);
    StartRotation = Camera->GetComponentQuat();
    EndRotation = RotationForPose(Destination);
    FlightRotation = StartRotation;
    FlightTime = 0;
    FlightDuration = FMath::Max(0.4, Duration);
    bFlying = true;
    bZooming = false;
    Caption = Label;
    LastInteraction = GetWorld()->GetRealTimeSeconds();
    UE_LOG(LogTemp, Display, TEXT("OASIS_INTERACTION fly label=%s duration=%.2f fromAltitude=%.2f toAltitude=%.2f"), *Label, Duration, StartLLH.Z, EndLLH.Z);
}

void AOasisPawn::FlyToScale(int32 Scale)
{
    static const TCHAR* Labels[] = {TEXT("Earth"), TEXT("China"), TEXT("Shanghai"), TEXT("Lujiazui")};
    Scale = FMath::Clamp(Scale, 0, 3);
    const double Duration = GetAltitude() > 1000000 && Scale == 3 ? 20.0 : 5.5;
    StartFlight(ScalePose(Scale), Duration, Labels[Scale]);
}

void AOasisPawn::FlyToPreset(int32 Preset)
{
    StartFlight(PresetPose(Preset), GetAltitude() > 1000000 ? 20.0 : 4.0, TEXT("Lujiazui"));
}

void AOasisPawn::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!World || !World->IsReady())
    {
#if PLATFORM_MAC
        DiscardOasisMacDrag();
#endif
        return;
    }
    const double WallTime = FPlatformTime::Seconds();
    const double WallDelta = WallTime - PreviousWallTime;
    PreviousWallTime = WallTime;
    const double Elapsed = WallTime - MetricsStart;
    if (Elapsed > 10) FrameMilliseconds.Add(WallDelta * 1000);
    if (FrameMilliseconds.Num() > 0 && FrameMilliseconds.Num() % 300 == 0) SaveMetrics();
    if (bFlying && !MenuOpen)
    {
        FlightTime += DeltaSeconds * FlightSpeed;
        const double T = FMath::Clamp(FlightTime / FlightDuration, 0.0, 1.0);
        const auto Smooth = [](double V) { V = FMath::Clamp(V, 0.0, 1.0); return V * V * V * (V * (V * 6 - 15) + 10); };
        const double Ease = Smooth(T);
        double Altitude = FMath::Exp(FMath::Lerp(FMath::Loge(FMath::Max(1.7, StartLLH.Z)), FMath::Loge(FMath::Max(1.7, EndLLH.Z)), Ease));
        FVector LLH = FMath::Lerp(StartLLH, EndLLH, Ease);
        if (!bZooming && StartLLH.Z < 8000 && EndLLH.Z < 8000 &&
            FMath::Min(StartLLH.Z, EndLLH.Z) < 100 && (Start.Eye - Destination.Eye).Size2D() > 1000)
        {
            // A low camera viewpoint must approach from above the authored
            // roofs, rather than cut diagonally through intermediate buildings.
            // This symmetric route also preserves position during reversal.
            const double Clearance = FMath::Max(750.0, FMath::Max(StartLLH.Z, EndLLH.Z));
            LLH = FMath::Lerp(StartLLH, EndLLH, Smooth((T - .25) / .5));
            Altitude = T < .25 ? FMath::Lerp(StartLLH.Z, Clearance, Smooth(T / .25)) :
                T > .75 ? FMath::Lerp(Clearance, EndLLH.Z, Smooth((T - .75) / .25)) : Clearance;
        }
        LLH.Z = Altitude;
        Pose.Eye = World->FromLLH(LLH);
        FlightRotation = FQuat::Slerp(StartRotation, EndRotation, Ease).GetNormalized();
        const double FocusDistance = FMath::Exp(FMath::Lerp(
            FMath::Loge(FMath::Max(1.0, (Start.Target - Start.Eye).Size())),
            FMath::Loge(FMath::Max(1.0, (Destination.Target - Destination.Eye).Size())), Ease));
        Pose.Target = Pose.Eye + FlightRotation.GetAxisX() * FocusDistance;
        Pose.Lens = FMath::Exp(FMath::Lerp(FMath::Loge(Start.Lens), FMath::Loge(Destination.Lens), Ease));
        if (T >= 1) { Pose = Destination; bFlying = false; bZooming = false; }
    }
#if PLATFORM_MAC
    APlayerController* PC = Cast<APlayerController>(GetController());
    if (!PC)
    {
        DiscardOasisMacDrag();
        return;
    }
    FIntPoint ViewportSize;
    PC->GetViewportSize(ViewportSize.X, ViewportSize.Y);
    TArray<FOasisMacClick> NativeClicks;
    ConsumeOasisMacClicks(NativeClicks, ViewportSize);
    for (const auto& Click : NativeClicks)
    {
        UE_LOG(LogTemp, Display, TEXT("OASIS_INPUT native_click count=%d x=%.1f y=%.1f"), Click.Count, Click.Position.X, Click.Position.Y);
        if (Click.Count % 2 == 0) DoubleClickPointerAt(Click.Position);
        else PressPointerAt(Click.Position);
    }
    const double NativeScroll = ConsumeOasisMacScroll();
    if (!FMath::IsNearlyZero(NativeScroll)) Dolly(FMath::Pow(0.80, NativeScroll));
    FVector2D NativeDrag;
    if (ConsumeOasisMacDrag(NativeDrag, ViewportSize) && !MenuOpen)
    {
        bFlying = false;
        bZooming = false;
        Orbit(NativeDrag);
        UE_LOG(LogTemp, Display, TEXT("OASIS_INTERACTION orbit dx=%.1f dy=%.1f"), NativeDrag.X, NativeDrag.Y);
    }
#else
    if (bPointerDown && !MenuOpen)
    {
        APlayerController* PC = Cast<APlayerController>(GetController());
        const FVector2D Pointer = MousePosition(PC);
        if (!bDragging && (Pointer - PressPosition).Size() > 5) { bDragging = true; bFlying = false; bZooming = false; }
        if (bDragging)
        {
            Orbit(Pointer - PreviousPointer);
        }
        PreviousPointer = Pointer;
    }
#endif
    ApplyPose();
}

void AOasisPawn::Orbit(const FVector2D& Delta)
{
    if (GetAltitude() > 10000)
    {
        FVector LLH = World->ToLLH(Pose.Eye);
        LLH.X -= Delta.X * 0.12;
        LLH.Y = FMath::Clamp(LLH.Y + Delta.Y * 0.12, -85.0, 85.0);
        Pose.Eye = World->FromLLH(LLH);
        Pose.Target = GetAltitude() > 8000000 ? World->EarthCenter() : World->FromLLH(FVector(LLH.X, LLH.Y, 0));
    }
    else
    {
        const FVector Offset = Pose.Eye - Pose.Target;
        const double Yaw = FMath::Atan2(Offset.Y, Offset.X) - FMath::DegreesToRadians(Delta.X * 0.2);
        const double Pitch = FMath::Clamp(FMath::Atan2(Offset.Z, FVector2D(Offset.X, Offset.Y).Size()) + FMath::DegreesToRadians(Delta.Y * 0.2), 0.003, 1.54);
        Pose.Eye = Pose.Target + FVector(FMath::Cos(Yaw) * FMath::Cos(Pitch), FMath::Sin(Yaw) * FMath::Cos(Pitch), FMath::Sin(Pitch)) * Offset.Size();
    }
    LastInteraction = GetWorld()->GetRealTimeSeconds();
}

FVector2D AOasisPawn::GetPointerPosition() const
{
    return MousePosition(Cast<APlayerController>(GetController()));
}

void AOasisPawn::ApplyPose()
{
    const FVector Current = GetActorLocation();
    if (GetAltitude() < 3000 && Current.Size() < 1000000 && (Pose.Eye - Current).Size() > 1)
    {
        FHitResult Hit;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(OasisCamera), true, this);
        if (GetWorld()->SweepSingleByChannel(Hit, Current, Pose.Eye, FQuat::Identity, ECC_WorldStatic, FCollisionShape::MakeSphere(50), Params))
        {
            Pose.Eye = Hit.Location + Hit.Normal * 150;
            bFlying = false;
            ++CollisionStops;
        }
    }
    if (GetAltitude() < 8000) Pose.Eye.Z = FMath::Max(Pose.Eye.Z, 170.0);
    SetActorLocation(Pose.Eye);
    Camera->SetWorldRotation(bFlying ? FlightRotation : RotationForPose(Pose));
    Camera->SetFieldOfView(FMath::RadiansToDegrees(2 * FMath::Atan(18.0 / Pose.Lens)));
    World->UpdateScale(GetAltitude());
}

FQuat AOasisPawn::RotationForPose(const FOasisPose& Value) const
{
    const FVector Direction = (Value.Target - Value.Eye).GetSafeNormal();
    const FVector LLH = World->ToLLH(Value.Eye);
    const FVector Up = LLH.Z > 10000 ?
        (World->FromLLH(LLH + FVector(0, .001, 0)) - Value.Eye).GetSafeNormal() : FVector::UpVector;
    return FRotationMatrix::MakeFromXZ(Direction, Up).ToQuat();
}

double AOasisPawn::GetAltitude() const
{
    return World ? World->ToLLH(Pose.Eye).Z : 20000000;
}

void AOasisPawn::PressPointer()
{
    PressPointerAt(GetPointerPosition());
}

void AOasisPawn::PressPointerAt(const FVector2D& Pointer)
{
    APlayerController* PC = Cast<APlayerController>(GetController());
    if (!PC) return;
    LastInteraction = GetWorld()->GetRealTimeSeconds();
    UE_LOG(LogTemp, Display, TEXT("OASIS_INPUT pointer_pressed x=%.1f y=%.1f menu=%d"), Pointer.X, Pointer.Y, MenuOpen);
    if (AOasisHUD* HUD = Cast<AOasisHUD>(PC->GetHUD()))
        if (HUD->HandleClick(Pointer)) return;
    if (MenuOpen) return;
    bPointerDown = true;
    bDragging = false;
    PreviousPointer = PressPosition = Pointer;
}

void AOasisPawn::DoubleClickPointer()
{
    DoubleClickPointerAt(GetPointerPosition());
}

void AOasisPawn::DoubleClickPointerAt(const FVector2D& Pointer)
{
    bPointerDown = false;
    bDragging = false;
    if (MenuOpen) return;
    APlayerController* PC = Cast<APlayerController>(GetController());
    if (!PC) return;
    LastInteraction = GetWorld()->GetRealTimeSeconds();
    const double Altitude = GetAltitude();
    UE_LOG(LogTemp, Display, TEXT("OASIS_INPUT double_click altitude=%.2f"), Altitude);
    if (Altitude > 10000)
    {
        FVector RayOrigin, RayDirection, Picked;
        const bool Deprojected = PC->DeprojectScreenPositionToWorld(Pointer.X, Pointer.Y, RayOrigin, RayDirection);
        const bool GlobeHit = Deprojected && World->PickGlobe(RayOrigin, RayDirection, Picked);
        if (GlobeHit)
        {
            if (Altitude > 8000000)
            {
                const FString Country = World->CountryAt(Picked);
                if (Country == TEXT("China")) FlyToScale(1);
                else
                {
                    FOasisPose NewPose;
                    NewPose.Eye = World->FromLLH(FVector(Picked.X, Picked.Y, 5500000));
                    NewPose.Target = World->FromLLH(FVector(Picked.X, Picked.Y, 0));
                    StartFlight(NewPose, 5.5, Country);
                }
            }
            else if (Altitude > 150000) FlyToScale(2);
            else FlyToScale(3);
            UE_LOG(LogTemp, Display, TEXT("OASIS_INTERACTION double_click lon=%.6f lat=%.6f"), Picked.X, Picked.Y);
        }
        else UE_LOG(LogTemp, Display, TEXT("OASIS_INPUT double_click_miss deprojected=%d"), Deprojected);
    }
    else
    {
        FOasisPose NewPose = Pose;
        NewPose.Eye = FMath::Lerp(Pose.Target, Pose.Eye, 0.4);
        StartFlight(NewPose, 1.5, Caption);
    }
}

void AOasisPawn::ReleasePointer() { bPointerDown = false; bDragging = false; }
void AOasisPawn::ZoomIn() { Dolly(0.80); }
void AOasisPawn::ZoomOut() { Dolly(1.25); }

void AOasisPawn::Dolly(double Factor)
{
    if (MenuOpen) return;
    LastInteraction = GetWorld()->GetRealTimeSeconds();
    FOasisPose Goal = bFlying && bZooming ? Destination : Pose;
    if (World->ToLLH(Goal.Eye).Z > 10000)
    {
        FVector LLH = World->ToLLH(Goal.Eye);
        LLH.Z = FMath::Clamp(LLH.Z * Factor, 900.0, 25000000.0);
        Goal.Eye = World->FromLLH(LLH);
    }
    else
    {
        const FVector Offset = Goal.Eye - Goal.Target;
        Goal.Eye = Goal.Target + Offset.GetSafeNormal() * FMath::Clamp(Offset.Size() * Factor, 1500.0, 2500000000.0);
    }
    StartFlight(Goal, .55, Caption);
    bZooming = true;
    UE_LOG(LogTemp, Display, TEXT("OASIS_INTERACTION wheel factor=%.2f altitude=%.2f"), Factor, GetAltitude());
}

void AOasisPawn::ToggleMenu() { MenuOpen = !MenuOpen; LastInteraction = GetWorld()->GetRealTimeSeconds(); }
void AOasisPawn::ToggleUI() { HideUI = !HideUI; }
void AOasisPawn::Reverse()
{
    if (bFlying)
    {
        Swap(Start, Destination);
        Swap(StartLLH, EndLLH);
        Swap(StartRotation, EndRotation);
        FlightTime = FlightDuration - FlightTime;
        Caption = EndLLH.Z > 8000000 ? TEXT("Earth") : EndLLH.Z > 150000 ? TEXT("China") : EndLLH.Z > 5000 ? TEXT("Shanghai") : TEXT("Lujiazui");
        LastInteraction = GetWorld()->GetRealTimeSeconds();
        UE_LOG(LogTemp, Display, TEXT("OASIS_INTERACTION reverse continuous_path"));
        return;
    }
    StartFlight(GetAltitude() < 100000 ? ScalePose(0) : ScalePose(3), 20, GetAltitude() < 100000 ? TEXT("Earth") : TEXT("Lujiazui"));
}

void AOasisPawn::SetLineWeight(float Weight)
{
    LineWeight = Weight;
    int32 Width = 0, Height = 1440;
    if (const APlayerController* PC = Cast<APlayerController>(GetController())) PC->GetViewportSize(Width, Height);
    if (World) World->SetInkWidth(Weight * FMath::Clamp(Height / 1440.f, .75f, 2.f));
    SavePreferences();
}
void AOasisPawn::SetRenderScale(int32 Percent)
{
    if (RenderScale != Percent)
    {
        SaveMetrics();
        FrameMilliseconds.Reset();
        MetricsStart = PreviousWallTime = FPlatformTime::Seconds();
    }
    RenderScale = Percent;
    if (auto* Value = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage"))) Value->Set(Percent, ECVF_SetByGameSetting);
    SavePreferences();
}
void AOasisPawn::SetAmbient(bool Enabled)
{
    AmbientEnabled = Enabled;
    if (auto* Value = IConsoleManager::Get().FindConsoleVariable(TEXT("r.AmbientOcclusionLevels"))) Value->Set(Enabled ? 2 : 0, ECVF_SetByGameSetting);
    SavePreferences();
}

void AOasisPawn::SetAutoHide(bool Enabled) { AutoHide = Enabled; SavePreferences(); }

void AOasisPawn::SavePreferences() const
{
    const FString Path = FPaths::ProjectSavedDir() / TEXT("OasisPreferences.ini");
    FConfigFile Preferences;
    Preferences.SetFloat(TEXT("Look"), TEXT("LineWeight"), LineWeight);
    Preferences.SetInt64(TEXT("Look"), TEXT("RenderScale"), RenderScale);
    Preferences.SetBool(TEXT("Look"), TEXT("AmbientEnabled"), AmbientEnabled);
    Preferences.SetBool(TEXT("Look"), TEXT("AutoHide"), AutoHide);
    if (!Preferences.Write(Path, false)) UE_LOG(LogTemp, Warning, TEXT("Oasis visual preferences could not be saved"));
}

void AOasisPawn::SaveMetrics() const
{
    if (FrameMilliseconds.Num() == 0) return;
    TArray<double> Sorted = FrameMilliseconds;
    Sorted.Sort();
    double Sum = 0;
    for (double Value : Sorted) Sum += Value;
    TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("scope"), TEXT("FPlatformTime wall frame intervals after ten-second warmup; includes pacing, not an isolated GPU timer"));
    int32 ViewWidth = 0, ViewHeight = 0;
    if (const APlayerController* PC = Cast<APlayerController>(GetController())) PC->GetViewportSize(ViewWidth, ViewHeight);
    Result->SetNumberField(TEXT("viewport_width"), ViewWidth);
    Result->SetNumberField(TEXT("viewport_height"), ViewHeight);
    if (const auto* Limit = IConsoleManager::Get().FindConsoleVariable(TEXT("t.MaxFPS"))) Result->SetNumberField(TEXT("frame_limit"), Limit->GetFloat());
    Result->SetNumberField(TEXT("samples"), Sorted.Num());
    Result->SetNumberField(TEXT("mean_frame_ms"), Sum / Sorted.Num());
    Result->SetNumberField(TEXT("mean_fps"), 1000.0 / (Sum / Sorted.Num()));
    Result->SetNumberField(TEXT("p95_frame_ms"), Sorted[FMath::Clamp(FMath::FloorToInt(Sorted.Num() * .95), 0, Sorted.Num() - 1)]);
    Result->SetNumberField(TEXT("p99_frame_ms"), Sorted[FMath::Clamp(FMath::FloorToInt(Sorted.Num() * .99), 0, Sorted.Num() - 1)]);
    Result->SetNumberField(TEXT("max_frame_ms"), Sorted.Last());
    Result->SetNumberField(TEXT("collision_stops"), CollisionStops);
    Result->SetNumberField(TEXT("render_scale_percent"), RenderScale);
    if (const auto* History = IConsoleManager::Get().FindConsoleVariable(TEXT("r.TSR.History.ScreenPercentage")))
        Result->SetNumberField(TEXT("tsr_history_percent"), History->GetFloat());
    Result->SetNumberField(TEXT("elapsed_seconds"), FPlatformTime::Seconds() - MetricsStart);
    FString Text;
    FJsonSerializer::Serialize(Result, TJsonWriterFactory<>::Create(&Text));
    FFileHelper::SaveStringToFile(Text, *(FPaths::ProjectSavedDir() / TEXT("OasisRuntimeMetrics.json")));
}

void AOasisPawn::EndPlay(const EEndPlayReason::Type Reason)
{
    SaveMetrics();
    Super::EndPlay(Reason);
}
