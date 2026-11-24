#pragma once

// The goldens' shape (tests/golden/<case>/linux/NN-<step>.json, dumped from
// the old GTK app's widget tree): per section (header, notice, game,
// characters, settings, task, dialog) the visible leaf elements in order:
//   label {t, tone, tip}   pill {t, pill, tip}   icon {t: icon name, tone}
//   button {id, t, icon, tip, cls, s}   check {id, t, tip, on, mixed, s}
//   switch {id, on, s}   choice {id, t, s}   expander {id, t, on}   spinner   progress
// flatten() turns the model's View into the same, so model_test compares them.

#include "model.h"

#include <map>
#include <string>
#include <vector>

namespace launcher::model {

struct Element {
    std::string kind;
    std::map<std::string, std::string> text; // t, id, tone, tip, icon, cls, pill
    std::map<std::string, bool> flags;       // s, on, mixed
    bool operator==(const Element&) const = default;
};
using Section = std::vector<Element>;
using Dump = std::map<std::string, Section>;

extern const char* const kSections[7];

const char* icon_name(Icon icon);
Dump flatten(const View& view);
// Every focusable item the view shows, in that order (menu entries too).
std::vector<Action> actions_of(const View& view);
std::optional<Dump> parse_dump(std::string_view json, std::string* error = nullptr);
std::string dump_json(const Dump& dump);
std::string element_text(const Element& e);

// The differences between a golden and the model's dump, as readable lines
// (none: equal). Elements are compared in order; `ignore_ids` are ids the
// model gives to items the old app named none (new: U14).
std::vector<std::string> compare(const Dump& golden, const Dump& model,
                                 const std::vector<std::string>& ignore_ids = {});

} // namespace launcher::model
