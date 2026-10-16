using UnrealBuildTool;

public class OasisNative : ModuleRules
{
    public OasisNative(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "InputCore", "CesiumRuntime",
            "ProceduralMeshComponent", "Json", "JsonUtilities", "Slate", "SlateCore"
        });
    }
}
