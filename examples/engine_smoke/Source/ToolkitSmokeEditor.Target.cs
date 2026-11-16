using UnrealBuildTool;

public class ToolkitSmokeEditorTarget : TargetRules
{
    public ToolkitSmokeEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("ToolkitSmoke");
    }
}
