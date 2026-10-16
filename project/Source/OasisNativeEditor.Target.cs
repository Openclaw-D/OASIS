using UnrealBuildTool;

public class OasisNativeEditorTarget : TargetRules
{
    public OasisNativeEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
        ExtraModuleNames.Add("OasisNative");
    }
}
