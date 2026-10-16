#include "OasisGameMode.h"
#include "OasisPawn.h"
#include "OasisHUD.h"

AOasisGameMode::AOasisGameMode()
{
    DefaultPawnClass = AOasisPawn::StaticClass();
    HUDClass = AOasisHUD::StaticClass();
}
