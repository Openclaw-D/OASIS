#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "OasisWorld.generated.h"

class ACesiumGeoreference;
class UProceduralMeshComponent;

struct FOasisBorder
{
    FString Name;
    TArray<FVector> Positions;
    TArray<FVector> Normals;
    TArray<FVector2D> LonLat;
};

UCLASS()
class OASISNATIVE_API AOasisWorld : public AActor
{
    GENERATED_BODY()
public:
    AOasisWorld();
    virtual void BeginPlay() override;
    void UpdateScale(double AltitudeMeters);
    FVector FromLLH(const FVector& LLH) const;
    FVector ToLLH(const FVector& Position) const;
    FVector EarthCenter() const;
    bool PickGlobe(const FVector& Origin, const FVector& Direction, FVector& LLH) const;
    FString CountryAt(const FVector& LLH) const;
    void SetInkWidth(float Width);
    const TArray<FOasisBorder>& GetBorders() const { return Borders; }
    const TArray<FOasisBorder>& GetCityPaths() const { return CityPaths; }
    bool IsReady() const { return Georeference != nullptr && Borders.Num() > 0; }

private:
    void BuildEarth();
    void LoadBorders();
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> Globe;
    UPROPERTY() TObjectPtr<ACesiumGeoreference> Georeference;
    UPROPERTY() TObjectPtr<class UMaterialInstanceDynamic> InkInstance;
    TArray<FOasisBorder> Borders;
    TArray<FOasisBorder> CityPaths;
    TArray<TWeakObjectPtr<AActor>> LocalActors;
    bool bLocalVisible = true;
};
