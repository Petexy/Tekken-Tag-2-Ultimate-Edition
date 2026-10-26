#include "cafe/ppc_ops.h"
PPC_FUNC(windows_alias_probe_orig) { ctx.r[3] = 1; (void)base; }
PPC_WEAK_ALIAS(windows_alias_probe);
