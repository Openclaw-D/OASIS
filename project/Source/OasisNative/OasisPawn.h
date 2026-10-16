#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "OasisPawn.generated.h"

class UCameraComponent;
class AOasisWorld;

struct FOasisPose
{
    FVector Eye = FVector::ZeroVector;
    FVector Target = FVector::ZeroVector;
    double Lens = 35;
};

UCLASS()
class OASISNATIVE_API AOasisPawn : public APawn
{
    GENERATED_BODY()
public:
    AOasisPawn();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    void FlyToScale(int32 Scale);
    void FlyToPreset(int32 Preset);
    void Reverse();
    void SetLineWeight(float Weight);
    void SetRenderScale(int32 Percent);
    void SetAmbient(bool Enabled);
    void SetAutoHide(bool Enabled);
    void SetFlightSpeed(float Speed) { FlightSpeed = Speed; }
    AOasisWorld* GetOasisWorld() const { return World; }
    double GetAltitude() const;
    const FVector& GetEye() const { return Pose.Eye; }
    FVector2D GetPointerPosition() const;
    bool MenuOpen = false;
    bool HideUI = false;
    bool AutoHide = true;
    float LastInteraction = 0;
    FString Caption = TEXT("Earth");
    float LineWeight = 1.5f;
    int32 RenderScale = 100;
    bool AmbientEnabled = true;
    bool IsFlying() const { return bFlying; }

private:
    void PressPointer();
    void DoubleClickPointer();
    void PressPointerAt(const FVector2D& Pointer);
    void DoubleClickPointerAt(const FVector2D& Pointer);
    void ReleasePointer();
    void ZoomIn();
    void ZoomOut();
    void Dolly(double Factor);
    void Orbit(const FVector2D& Delta);
    void ToggleMenu();
    void ToggleUI();
    void StartFlight(const FOasisPose& Destination, double Duration, const FString& Label);
    void ApplyPose();
    FQuat RotationForPose(const FOasisPose& Value) const;
    void SaveMetrics() const;
    void SavePreferences() const;
    FOasisPose ScalePose(int32 Scale) const;
    FOasisPose PresetPose(int32 Preset) const;
    UPROPERTY() TObjectPtr<UCameraComponent> Camera;
    UPROPERTY() TObjectPtr<AOasisWorld> World;
    FOasisPose Pose, Start, Destination;
    FVector StartLLH, EndLLH;
    FQuat StartRotation = FQuat::Identity, EndRotation = FQuat::Identity, FlightRotation = FQuat::Identity;
    double FlightTime = 0, FlightDuration = 1;
    float FlightSpeed = 1;
    bool bFlying = false, bZooming = false, bPointerDown = false, bDragging = false;
    FVector2D PreviousPointer, PressPosition;
    TArray<double> FrameMilliseconds;
    double MetricsStart = 0;
    double PreviousWallTime = 0;
    int32 CollisionStops = 0;
};
