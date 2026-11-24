#pragma once

// model_test's checks: a failure is counted and printed, the test goes on.

#include <cstdio>
#include <sstream>
#include <string>

namespace launcher::model::testing {

inline int failures = 0;
inline int checks = 0;      // checks made
inline std::string current; // what is being tested: printed with a failure

inline void fail(const char* file, int line, const std::string& what) {
    ++failures;
    std::fprintf(stderr, "FAILED %s:%d [%s]: %s\n", file, line, current.c_str(), what.c_str());
}

} // namespace launcher::model::testing

#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        ++::launcher::model::testing::checks;                                                                          \
        if (!(cond)) ::launcher::model::testing::fail(__FILE__, __LINE__, #cond);                                      \
    } while (0)

#define CHECK_EQ(a, b)                                                                                                 \
    do {                                                                                                               \
        const auto& a_ = (a);                                                                                          \
        const auto& b_ = (b);                                                                                          \
        ++::launcher::model::testing::checks;                                                                          \
        if (!(a_ == b_)) {                                                                                             \
            std::ostringstream s_;                                                                                     \
            s_ << #a << " == " << #b << "\n    " << a_ << "\n    vs " << b_;                                           \
            ::launcher::model::testing::fail(__FILE__, __LINE__, s_.str());                                            \
        }                                                                                                              \
    } while (0)
