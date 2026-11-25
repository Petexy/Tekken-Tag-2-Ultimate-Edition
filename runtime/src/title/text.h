#pragma once

// The title's text banks ("NTXB" entries of data003: per language, the
// texts of a part of the game). Each text is a record: its key
// ("common_4"), padded to four with at least one zero byte; two bytes; its
// length in characters (big-endian); its UTF-8 text, then the English text
// it was translated from (cut to 32 bytes), each padded to four with at
// least two zero bytes. The bank's index points at the records, so a text
// can change in place within its space.

#include <cstddef>
#include <cstdint>
#include <set>
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
// 360's, START, SELECT and BACK) to the buttons' icons, which follow the
// controller. Returns how many texts changed.
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

// The number of texts (records with a key) of the bank.
size_t text_count(const std::vector<uint8_t>& bank);

// The banks the title reads for a language it has no texts of in a part of
// the game (the Wii U's Russian Practice texts are missing: their bank has
// none) take that part's English bank's texts: `banks` in an archive's
// order, each part's in the languages' order. Returns the indices of the
// banks changed (their language byte kept).
std::vector<size_t> fill_missing_texts(std::vector<std::vector<uint8_t>*> banks);

} // namespace cafe::title::text
