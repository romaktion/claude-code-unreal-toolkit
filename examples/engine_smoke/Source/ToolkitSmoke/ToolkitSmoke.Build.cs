using UnrealBuildTool;

public class ToolkitSmoke : ModuleRules
{
    public ToolkitSmoke(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.Add("Core");
    }
}
