#include "OasisWorld.h"
#include "CesiumGeoreference.h"
#include "ProceduralMeshComponent.h"
#include "EngineUtils.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/PostProcessVolume.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

AOasisWorld::AOasisWorld()
{
    Globe = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("WGS84Ellipsoid"));
    RootComponent = Globe;
    Globe->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Globe->SetRenderCustomDepth(true);
    Globe->SetCustomDepthStencilValue(5);
    Globe->SetCastShadow(false);
}

void AOasisWorld::BeginPlay()
{
    Super::BeginPlay();
    Georeference = ACesiumGeoreference::GetDefaultGeoreference(this);
    Georeference->SetOriginLongitudeLatitudeHeight(FVector(121.501909, 31.2364814, 0));
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
        if (It->ActorHasTag(TEXT("OasisLocal"))) LocalActors.Add(*It);
    BuildEarth();
    LoadBorders();
    for (TActorIterator<APostProcessVolume> It(GetWorld()); It; ++It)
        for (auto& Blendable : It->Settings.WeightedBlendables.Array)
            if (UMaterialInterface* Material = Cast<UMaterialInterface>(Blendable.Object))
                if (Material->GetName() == TEXT("PP_OasisInk"))
                {
                    InkInstance = UMaterialInstanceDynamic::Create(Material, this);
                    Blendable.Object = InkInstance;
                }
    UpdateScale(20000000);
    UE_LOG(LogTemp, Display, TEXT("OASIS_WORLD_READY borders=%d localActors=%d"), Borders.Num(), LocalActors.Num());
}

FVector AOasisWorld::FromLLH(const FVector& LLH) const
{
    return Georeference->TransformLongitudeLatitudeHeightPositionToUnreal(LLH);
}

FVector AOasisWorld::ToLLH(const FVector& Position) const
{
    return Georeference->TransformUnrealPositionToLongitudeLatitudeHeight(Position);
}

FVector AOasisWorld::EarthCenter() const
{
    return Georeference->TransformEarthCenteredEarthFixedPositionToUnreal(FVector::ZeroVector);
}

void AOasisWorld::SetInkWidth(float Width)
{
    if (InkInstance) InkInstance->SetScalarParameterValue(TEXT("LineWidth"), Width);
}

bool AOasisWorld::PickGlobe(const FVector& Origin, const FVector& Direction, FVector& LLH) const
{
    const FVector O = Georeference->TransformUnrealPositionToEarthCenteredEarthFixed(Origin);
    const FVector D = Georeference->TransformUnrealDirectionToEarthCenteredEarthFixed(Direction).GetSafeNormal();
    const FVector InverseRadii(1.0 / 6378137.0, 1.0 / 6378137.0, 1.0 / 6356752.314245179);
    const FVector Q = O * InverseRadii, V = D * InverseRadii;
    const double A = FVector::DotProduct(V, V), B = 2 * FVector::DotProduct(Q, V), C = Q.SizeSquared() - 1;
    const double Discriminant = B * B - 4 * A * C;
    if (Discriminant < 0 || A < 1e-30) return false;
    double T = (-B - FMath::Sqrt(Discriminant)) / (2 * A);
    if (T < 0) T = (-B + FMath::Sqrt(Discriminant)) / (2 * A);
    if (T < 0) return false;
    LLH = ToLLH(Georeference->TransformEarthCenteredEarthFixedPositionToUnreal(O + D * T));
    return true;
}

FString AOasisWorld::CountryAt(const FVector& LLH) const
{
    const FVector2D Point(LLH.X, LLH.Y);
    for (const auto& Border : Borders)
    {
        bool Inside = false;
        for (int32 I = 0, J = Border.LonLat.Num() - 1; I < Border.LonLat.Num(); J = I++)
        {
            const FVector2D& A = Border.LonLat[I];
            const FVector2D& B = Border.LonLat[J];
            if ((A.Y > Point.Y) != (B.Y > Point.Y) &&
                Point.X < (B.X - A.X) * (Point.Y - A.Y) / (B.Y - A.Y) + A.X) Inside = !Inside;
        }
        if (Inside) return Border.Name;
    }
    return TEXT("Earth");
}

void AOasisWorld::BuildEarth()
{
    constexpr int32 LatitudeSteps = 96;
    constexpr int32 LongitudeSteps = 192;
    const FVector Center = EarthCenter();
    SetActorLocation(Center);
    TArray<FVector> Vertices, Normals;
    TArray<int32> Triangles;
    TArray<FVector2D> UV;
    TArray<FLinearColor> Colors;
    TArray<FProcMeshTangent> Tangents;
    for (int32 Y = 0; Y <= LatitudeSteps; ++Y)
    {
        const double Lat = -90.0 + 180.0 * Y / LatitudeSteps;
        for (int32 X = 0; X <= LongitudeSteps; ++X)
        {
            const double Lon = -180.0 + 360.0 * X / LongitudeSteps;
            const FVector Surface = FromLLH(FVector(Lon, Lat, -2));
            Vertices.Add(Surface - Center);
            Normals.Add((FromLLH(FVector(Lon, Lat, 8)) - Surface).GetSafeNormal());
            UV.Add(FVector2D(double(X) / LongitudeSteps, double(Y) / LatitudeSteps));
        }
    }
    for (int32 Y = 0; Y < LatitudeSteps; ++Y)
        for (int32 X = 0; X < LongitudeSteps; ++X)
        {
            const int32 A = Y * (LongitudeSteps + 1) + X;
            const int32 B = A + 1, C = A + LongitudeSteps + 1, D = C + 1;
            Triangles.Append({A, C, B, B, C, D});
        }
    Globe->CreateMeshSection_LinearColor(0, Vertices, Triangles, Normals, UV, Colors, Tangents, false);
    Globe->SetMaterial(0, LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Oasis/Materials/M_Mono_Globe.M_Mono_Globe")));
}

void AOasisWorld::LoadBorders()
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *(FPaths::ProjectContentDir() / TEXT("NativeData/earth-overview.geojson"))))
    {
        UE_LOG(LogTemp, Error, TEXT("Oasis public geography payload is missing"));
        return;
    }
    TSharedPtr<FJsonObject> Data;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Data)) return;
    auto AddRing = [this](const TArray<TSharedPtr<FJsonValue>>& Coordinates, const FString& Name)
    {
        FOasisBorder Border;
        Border.Name = Name;
        for (const auto& Point : Coordinates)
        {
            const auto& Pair = Point->AsArray();
            const FVector LLH(Pair[0]->AsNumber(), Pair[1]->AsNumber(), 100);
            const FVector Position = FromLLH(LLH);
            Border.Positions.Add(Position);
            Border.LonLat.Add(FVector2D(LLH.X, LLH.Y));
            Border.Normals.Add((FromLLH(LLH + FVector(0, 0, 10)) - Position).GetSafeNormal());
        }
        if (Border.Positions.Num() > 1) Borders.Add(MoveTemp(Border));
    };
    for (const auto& Item : Data->GetArrayField(TEXT("features")))
    {
        const auto Feature = Item->AsObject();
        const auto Geometry = Feature->GetObjectField(TEXT("geometry"));
        FString Name = Feature->GetObjectField(TEXT("properties"))->GetStringField(TEXT("name"));
        if (Name == TEXT("People's Republic of China")) Name = TEXT("China");
        const auto& Coordinates = Geometry->GetArrayField(TEXT("coordinates"));
        if (Geometry->GetStringField(TEXT("type")) == TEXT("Polygon"))
            for (const auto& Ring : Coordinates) AddRing(Ring->AsArray(), Name);
        else
            for (const auto& Polygon : Coordinates)
                for (const auto& Ring : Polygon->AsArray()) AddRing(Ring->AsArray(), Name);
    }
    FString CityText;
    TSharedPtr<FJsonObject> City;
    if (FFileHelper::LoadFileToString(CityText, *(FPaths::ProjectContentDir() / TEXT("NativeData/shanghai-overview.json"))) &&
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(CityText), City))
        for (const auto& Path : City->GetArrayField(TEXT("paths")))
        {
            FOasisBorder Line;
            for (const auto& Point : Path->AsArray())
            {
                const auto& Pair = Point->AsArray();
                Line.Positions.Add(FromLLH(FVector(Pair[0]->AsNumber(), Pair[1]->AsNumber(), 20)));
            }
            CityPaths.Add(MoveTemp(Line));
        }
}

void AOasisWorld::UpdateScale(double AltitudeMeters)
{
    Globe->SetVisibility(AltitudeMeters > 8000);
    const bool bShowLocal = AltitudeMeters < 150000;
    if (bShowLocal != bLocalVisible)
    {
        for (const auto& Actor : LocalActors)
            if (Actor.IsValid()) Actor->SetActorHiddenInGame(!bShowLocal);
        bLocalVisible = bShowLocal;
    }
}
