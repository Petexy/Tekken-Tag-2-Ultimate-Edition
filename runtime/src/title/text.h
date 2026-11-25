#pragma once

// The title's text banks ("NTXB" entries of data003: per language, the
// texts of a part of the game). Each text is a record: two bytes; its
// length in characters (big-endian); its UTF-8 text, then the English text
// it was translated from (cut to 32 bytes), each padded to four with at
// least two zero bytes; its key ("common_4"), padded to four with at least
// one zero byte. The bank's index points at the records, so a text can
// change in place within its space; a key is followed by the next record.

#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace cafe::title::text {

// The code points the texts get for the buttons, by the button's place:
// symbols no text of the game uses, which both fonts the texts are drawn
// with have (the main font's own icons, E024 and on, are missing from the
// plain one). Their glyphs become the icons (presentation.cpp).
constexpr char32_t kRightButton = 0x00A3, kBottomButton = 0x00A5, kTopButton = 0x00A2, kLeftButton = 0x00AA; // £ ¥ ¢ ª
constexpr char32_t kStartButton = 0xFF3C, kSelectButton = 0x00B3, kPad = 0x00BB;                             // ＼ ³ »

bool is_bank(const std::vector<uint8_t>& contents);

// Rewrites the Wii U's button names in the bank's texts (the + and -
// buttons, A B X Y, the +Control Pad; in English, French, Italian, German
// and Spanish; in Russian, whose texts are the PlayStation 3's and Xbox
// 360's, START, SELECT and BACK, and our translations' names) to the
// buttons' icons, which follow the controller. Returns how many texts
// changed.
int show_button_icons(std::vector<uint8_t>& bank);

// Adds the code points of the bank's texts to `used`.
void code_points(const std::vector<uint8_t>& bank, std::set<char32_t>& used);

// A bank's language (its byte 6): data003 has each part's banks in this
// order, one per language.
enum BankLanguage : uint8_t {
    kBankJapanese = 1, kBankEnglish, kBankEnglishAgain, kBankFrench, kBankItalian, kBankGerman, kBankSpanish,
    kBankKorean, kBankChinese, kBankRussian
};
uint8_t bank_language(const std::vector<uint8_t>& bank); // 0: not a bank

// A text's markup, in order: its control codes (a code of U+FFF0 on with
// its arguments, the code points after it: the title's table of them has
// two for U+FFF2, a colour, none for U+FFFF and one for the others), line
// breaks and other codes below U+0020, the private-use code points the
// fonts draw as icons, the button names show_button_icons turns into icons
// (as those icons) and the symbols that stand for inputs (☆【】↑↓). A
// translation keeps its original's.
std::u32string markup(std::string_view text);

// The hash a record's header holds of its text (in its first two bytes, the
// low byte first): per code point c, h = T(h) ^ c, T a fixed linear map.
uint16_t text_hash(std::string_view text);

// A translation of a record of a part's bank, by the record's key.
struct Translation {
    std::string_view key, text;
};

// Our Russian for the texts the Wii U's Russian banks lack (text_russian.inc):
// where a Russian bank of the game has the same English text under another
// number, the game's own Russian text of it fits that record too and has no
// entry here. Where ours would say what a record of the player's Russian
// banks says (a mode's name, a term), it names that record instead (see
// with_references).
std::span<const Translation> russian_texts();

// A text with its references to records of the player's Russian banks
// expanded: "{common_4}" stands for that record's text (spaces at its ends
// dropped), "{common_4:upper}" for it in capitals, "{common_4:capital}"
// for it with only its first letter a capital (Latin and Cyrillic letters).
// `russian` gives a key's text. Nothing if a reference is not well formed or
// names a record `russian` has no text for. (Our texts have no other
// braces.)
std::optional<std::string> with_references(
    std::string_view text, const std::function<std::optional<std::string_view>(std::string_view key)>& russian);

// The Russian banks lack texts the other languages have (the Wii U's own:
// of Practice, all; of the menus, the special modes'; ...). Each gets the
// English bank's records of the numbers it has none of, each with its text
// in Russian: `russian`'s for its key (its references expanded from the
// Russian banks of `banks` as they were), else the text a Russian bank of
// the archive has for the same English text (its most frequent one), else
// the English one; a Russian text whose markup is not the English text's,
// or one naming a record the Russian banks lack, is left out (English
// stays). `banks` in an archive's order, each part's in the languages'
// order.
struct Filled {
    std::vector<size_t> banks;               // the banks changed (their language byte kept, rebuilt with their index)
    std::vector<std::string> kept_english;   // the keys of our texts left out: their markup is not English's
    std::vector<std::string> unresolved;     // ... and of those left out as they name a record the banks lack
};
Filled fill_missing_texts(std::vector<std::vector<uint8_t>*> banks,
                          std::span<const Translation> russian = russian_texts());

// Our Polish (text_polish.inc), by key: of each English text, the record a
// work list met it in first, and the others of that text where it needs
// other words there.
std::span<const Translation> polish_texts();

// Polish, which the Wii U has none of: the title shows the English banks,
// and their records get our Polish (`polish`'s for their key, else
// `polish`'s for another key whose English record has the same English
// text in the banks), else stay English; one whose markup is not the
// English text's (its line breaks aside: lines may break elsewhere, and
// table 1 counts the new text's) stays English. `banks` in an archive's
// order, each part's in the languages' order. (Records without a key, the
// arcade texts the other languages show in English too, stay English.)
Filled put_polish(std::vector<std::vector<uint8_t>*> banks, std::span<const Translation> polish = polish_texts());

// The bank with texts changed: `change` gets each record's text (table 1's
// order) and gives its new text, or nothing to keep it; a changed record as
// put_polish's (its header and line count its text's). Nothing when it is
// not a bank this reads.
std::optional<std::vector<uint8_t>> with_texts(
    const std::vector<uint8_t>& bank,
    const std::function<std::optional<std::string>(size_t record, std::string_view text)>& change);

} // namespace cafe::title::text
