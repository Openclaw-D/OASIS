#pragma once
#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "OasisHUD.generated.h"

class AOasisPawn;

struct FOasisButton
{
    FBox2D Bounds;
    TFunction<void()> Action;
};

UCLASS()
class OASISNATIVE_API AOasisHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
    bool HandleClick(const FVector2D& Position);
private:
    void DrawGeography(AOasisPawn* Pawn);
    void Text(const FString& Value, FVector2D Position, float Size, FLinearColor Color);
    void Button(const FString& Label, FVector2D Position, float Width, TFunction<void()> Action);
    TArray<FOasisButton> Buttons;
    float Scale = 1;
    float MenuFade = 0;
};
