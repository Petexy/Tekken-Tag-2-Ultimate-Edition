#pragma once

#include "facts.h"

namespace launcher::model::testing {

// The controllers' unit tests; `golden`: the golden cases (their fixtures are used), `scratch`: a folder of
// the test's own.
void units(const fs::path& golden, const fs::path& scratch);

} // namespace launcher::model::testing
