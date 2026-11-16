#include "Math/UnrealMathUtility.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
    FToolkitClampTest,
    "ToolkitSmoke.Math.ClampAmmo",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FToolkitClampTest::RunTest(const FString& Parameters)
{
    TestEqual(TEXT("Negative ammo clamps to zero"), FMath::Clamp(-1, 0, 30), 0);
    TestEqual(TEXT("Overfilled magazine clamps to capacity"), FMath::Clamp(31, 0, 30), 30);
    TestEqual(TEXT("Valid ammo stays unchanged"), FMath::Clamp(11, 0, 30), 11);
    return true;
}

#endif
