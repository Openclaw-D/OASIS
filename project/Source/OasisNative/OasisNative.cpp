#include "Modules/ModuleManager.h"
#include "OasisMacPointer.h"

class FOasisModule : public FDefaultGameModuleImpl
{
public:
    virtual void StartupModule() override
    {
#if PLATFORM_MAC
        InstallOasisMacPointer();
#endif
    }
    virtual void ShutdownModule() override
    {
#if PLATFORM_MAC
        RemoveOasisMacPointer();
#endif
    }
};

IMPLEMENT_PRIMARY_GAME_MODULE(FOasisModule, OasisNative, "OasisNative");
