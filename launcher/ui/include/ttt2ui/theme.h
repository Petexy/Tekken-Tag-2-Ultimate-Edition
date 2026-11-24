// The look ("Tag Split" v2, local/scratch/launcher2/concepts/tagsplit2): EVERY constant of it lives here - palette,
// split ratios, the seam's 12 degrees, plate offsets, metrics, durations, spring constants, font roles and text
// styles - so a change the player asks for is one edit. The toolkit's code reads only these names; nothing here
// knows a screen of the launcher.
//
// Units: points (design pixels of the 1280 x 800 stage at scale 1). Times: seconds.
#pragma once

#include "ttt2ui/geometry.h"

namespace ttt2::ui::theme {

// ---- stage and seam geometry -------------------------------------------------------------------------------------
constexpr float kStageWidth = 1280, kStageHeight = 800;
constexpr float kSeamDegrees = 12;
constexpr float kSeamTan = 0.21255656167f;  // tan(12 degrees): every skewed shape and the seam lean by it
constexpr float kTopBand = 76;              // the neutral top bar (tabs)
constexpr float kBottomBand = 48;           // the neutral prompt bar
constexpr float kSeamCenterY = 414;         // stage y where the split value C is measured
constexpr float kGutter = 30;               // seam -> plate edge
constexpr float kPlatePad = 18;             // plate edge -> content
constexpr float kSeamGap = kGutter + kPlatePad;  // content keeps this far from the seam
constexpr float kPlateTop = 88;             // stage y
constexpr float kPlateBottomGap = 64;       // prompt band top - plate bottom (688 of 800: room for the task strip)
constexpr float kPlateBottomGapTask = 12;   // ... while a task fills the screen (740)
constexpr float kPlateSide = 20;            // plate outer edges from the window's sides
constexpr float kLean = 10;                 // the seam moves this far toward blue while the focus is there

// The split value C as a share of the stage width (Home 640, first run/task 576, Fighters 794, Settings 704,
// file browser 742, dialog band 612 at 1280).
namespace split {
constexpr float kHome = 640.f / 1280, kSetup = 576.f / 1280, kFighters = 794.f / 1280, kSettings = 704.f / 1280,
                kPicker = 742.f / 1280, kDialog = 612.f / 1280;
}  // namespace split

// ---- palette (the mock's CSS tokens) -------------------------------------------------------------------------------
namespace color {
constexpr Color kBackground = rgb(0x05060a), kWindow = rgb(0x030306);
constexpr Color kRed = rgb(0xff2a55), kRed2 = rgb(0xd6123f), kRed3 = rgb(0x5e0a1f);
constexpr Color kBlue = rgb(0x2d80ff), kBlue2 = rgb(0x155ae2), kBlue3 = rgb(0x0a2366), kCyan = rgb(0x62d4ff);
constexpr Color kText = rgb(0xf4f6fb), kDim = rgb(0xaab2c4), kFaint = rgb(0x7d859b);
constexpr Color kRedDim = rgb(0xd9b3bd), kRedFaint = rgb(0xa4808a), kBlueDim = rgb(0xb3c4e0),
                kBlueFaint = rgb(0x7f93b6);
constexpr Color kOk = rgb(0x3fe7a1), kWarn = rgb(0xffc843), kBad = rgb(0xff6b7e);
constexpr Color kRedLabel = rgb(0xff9db1), kBlueLabel = rgb(0x9cc6ff);
constexpr Color kTabIdle = rgb(0x7a8296), kTabHover = rgb(0xc9cfdc);
constexpr Color kBand = rgba(7, 8, 13, .95f);
// Background fields (crimson: far -> seam; blue: seam -> far).
constexpr Color kFieldRedFar = rgba(34, 3, 11, .95f), kFieldRedMid = rgba(74, 6, 24, .9f),
                kFieldRedSeam = rgba(150, 12, 46, .85f);
constexpr Color kFieldBlueSeam = rgba(20, 62, 190, .85f), kFieldBlueMid = rgba(10, 32, 104, .88f),
                kFieldBlueFar = rgba(4, 13, 44, .95f);
// Plates.
constexpr Color kPlateRedOuter = rgba(12, 2, 6, .8f), kPlateRedSeam = rgba(30, 4, 13, .74f);
constexpr Color kPlateBlueSeam = rgba(5, 14, 40, .74f), kPlateBlueOuter = rgba(3, 7, 20, .8f);
constexpr Color kPlateRedStroke = rgba(255, 120, 150, .16f), kPlateBlueStroke = rgba(130, 180, 255, .16f);
constexpr Color kPlateRedEdge = rgba(255, 95, 130, .6f), kPlateBlueEdge = rgba(110, 170, 255, .6f);
constexpr Color kSeamLine = rgba(255, 255, 255, .92f), kSeamFaint = rgba(255, 255, 255, .16f);
// Surfaces of skewed items (rows, buttons): rest / focused.
constexpr Color kRowFill = rgba(255, 255, 255, .045f), kRowStrokeRed = rgba(255, 120, 150, .24f);
constexpr Color kRowFocusA = rgba(255, 42, 85, .62f), kRowFocusB = rgba(150, 10, 40, .42f),
                kRowFocusStroke = rgba(255, 200, 212, .95f);
constexpr Color kSlabA = rgb(0xff4a6e), kSlabB = rgb(0xe8173f), kSlabC = rgb(0x9e0b2c);
constexpr Color kKeycap = rgb(0xe9ecf4), kKeycapText = rgb(0x0b0d14), kKeycapShadow = rgb(0x7f879a);
constexpr Color kPadGlyphBase = rgb(0x171b27);
constexpr Color kXboxA = rgb(0x6fd77a), kXboxB = rgb(0xff6b6b), kXboxX = rgb(0x5aa5ff), kXboxY = rgb(0xffd04d);
constexpr Color kPsCross = rgb(0x8fb6ff), kPsCircle = rgb(0xff7488), kPsSquare = rgb(0xf59ad2),
                kPsTriangle = rgb(0x4fe0c0);
constexpr Color kScrim = rgba(3, 4, 8, .74f);
constexpr Color kScrollBar = rgba(255, 255, 255, .22f), kScrollBarActive = rgba(255, 255, 255, .5f);
}  // namespace color

// ---- fonts -------------------------------------------------------------------------------------------------------
enum class Font {
    DisplayBlackItalic,      // Barlow Condensed 900 italic: tabs, big titles, tile codes
    DisplayExtraBoldItalic,  // 800 italic: rows, buttons, labels
    DisplayBoldItalic,       // 700 italic: pills, values, small caps labels, prompts
    DisplayExtraBold,        // 800 upright: key caps
    Body,                    // Barlow 500: paragraphs
    BodySemiBold,            // Barlow 600
    BodyBold,                // Barlow 700: keyboard glyph caps
    Mono,                    // JetBrains Mono 400: paths, versions, log
    MonoBold,                // JetBrains Mono 700
    Count
};
// The built-in font file of each role (launcher/ui/fonts, embedded).
constexpr const char* kFontFiles[] = {
    "BarlowCondensed/BarlowCondensed-BlackItalic.ttf",     "BarlowCondensed/BarlowCondensed-ExtraBoldItalic.ttf",
    "BarlowCondensed/BarlowCondensed-BoldItalic.ttf",      "BarlowCondensed/BarlowCondensed-ExtraBold.ttf",
    "Barlow/Barlow-Medium.ttf",                            "Barlow/Barlow-SemiBold.ttf",
    "Barlow/Barlow-Bold.ttf",                              "JetBrainsMono/JetBrainsMono-Regular.ttf",
    "JetBrainsMono/JetBrainsMono-Bold.ttf"};
static_assert(sizeof kFontFiles / sizeof kFontFiles[0] == static_cast<int>(Font::Count));

// Coverage gamma applied when glyphs are baked (light text on the dark look reads thin without it).
constexpr float kTextGamma = 1.35f;
// Pixel sizes are quantised to this step below kTextQuantSmallLimit px, and to whole pixels above.
constexpr float kTextQuantSmall = 0.5f, kTextQuantSmallLimit = 16;
// Horizontal oversampling of glyphs up to this pixel size (sub-pixel positions).
constexpr float kTextOversampleLimit = 24;

struct TextStyle {
    Font font = Font::Body;
    float size = 14;          // points
    float tracking = 0;       // letter spacing in em
    bool upper = false;       // shown in capitals
    float line_height = 1.2f; // multiple of size
};
namespace text {
constexpr TextStyle kBrand{Font::DisplayExtraBoldItalic, 14, .24f, true, 1.05f};
constexpr TextStyle kTab{Font::DisplayBlackItalic, 31, .03f, true, 1};
constexpr TextStyle kTabBadge{Font::DisplayExtraBoldItalic, 13, 0, false, 1};
constexpr TextStyle kVersion{Font::DisplayBoldItalic, 13, .18f, true, 1};
constexpr TextStyle kIconButton{Font::DisplayBoldItalic, 13, .14f, true, 1};
constexpr TextStyle kSlabBig{Font::DisplayBlackItalic, 96, .01f, true, 1};
constexpr TextStyle kSlabSmall{Font::DisplayBoldItalic, 15, .14f, true, 1.1f};
constexpr TextStyle kMenuTitle{Font::DisplayExtraBoldItalic, 23, .05f, true, 1};
constexpr TextStyle kMenuValue{Font::DisplayBoldItalic, 14, .12f, true, 1};
constexpr TextStyle kChevron{Font::DisplayBlackItalic, 28, 0, false, 1};
constexpr TextStyle kLabel{Font::DisplayExtraBoldItalic, 13, .3f, true, 1};
constexpr TextStyle kLabelEm{Font::DisplayExtraBoldItalic, 13, .18f, true, 1};
constexpr TextStyle kPill{Font::DisplayBoldItalic, 13, .14f, true, 1};
constexpr TextStyle kKick{Font::BodySemiBold, 14, 0, false, 1};
constexpr TextStyle kTitleLine{Font::DisplayBlackItalic, 70, -.005f, true, .88f};
constexpr TextStyle kEdition{Font::DisplayExtraBoldItalic, 19, .46f, true, 1};
constexpr TextStyle kFactKey{Font::DisplayBoldItalic, 12.5f, .2f, true, 1.44f};
constexpr TextStyle kFactValue{Font::Mono, 13.5f, 0, false, 1.33f};
constexpr TextStyle kFactValueUi{Font::BodySemiBold, 13.5f, 0, false, 1.33f};
constexpr TextStyle kExplainTitle{Font::DisplayExtraBoldItalic, 15, .2f, true, 1};
constexpr TextStyle kExplainText{Font::Body, 14, 0, false, 1.4f};
constexpr TextStyle kPara{Font::Body, 14.5f, 0, false, 1.45f};
constexpr TextStyle kParaSmall{Font::Body, 13.5f, 0, false, 1.45f};
constexpr TextStyle kWarn{Font::Body, 13.5f, 0, false, 1.4f};
constexpr TextStyle kBig{Font::DisplayBlackItalic, 54, .005f, true, .92f};
constexpr TextStyle kFighterName{Font::DisplayBlackItalic, 74, -.005f, true, .9f};
constexpr TextStyle kLastName{Font::DisplayExtraBoldItalic, 30, .2f, true, 1};
constexpr TextStyle kGroupTitle{Font::DisplayBlackItalic, 27, .04f, true, 1};
constexpr TextStyle kGroupCount{Font::DisplayBoldItalic, 12.5f, .14f, true, 1};
constexpr TextStyle kTileCode{Font::DisplayBlackItalic, 30, .01f, true, 1};
constexpr TextStyle kTileName{Font::DisplayBoldItalic, 11.5f, .06f, true, 1};
constexpr TextStyle kTileTag{Font::DisplayExtraBoldItalic, 10, .06f, true, 1};
constexpr TextStyle kButton{Font::DisplayExtraBoldItalic, 20, .06f, true, 1};
constexpr TextStyle kButtonSmall{Font::DisplayExtraBoldItalic, 17, .06f, true, 1};
constexpr TextStyle kButtonTiny{Font::DisplayExtraBoldItalic, 13.5f, .06f, true, 1};
constexpr TextStyle kSection{Font::DisplayBlackItalic, 21, .06f, true, 1};
constexpr TextStyle kSettingTitle{Font::DisplayExtraBoldItalic, 21, .05f, true, 1};
constexpr TextStyle kSettingValue{Font::DisplayExtraBoldItalic, 17, .08f, true, 1};
constexpr TextStyle kKeyName{Font::BodySemiBold, 14, 0, false, 1};
constexpr TextStyle kKeyCap{Font::DisplayExtraBold, 15, .04f, false, 1};
constexpr TextStyle kKeyCapBig{Font::DisplayExtraBold, 24, .04f, false, 1};
constexpr TextStyle kGlyphKey{Font::BodyBold, 12, 0, false, 1};
constexpr TextStyle kGlyphPad{Font::Body, 13, 0, false, 1};
constexpr TextStyle kHint{Font::DisplayBoldItalic, 15, .12f, true, 1};
constexpr TextStyle kStepName{Font::DisplayExtraBoldItalic, 18, .1f, true, 1};
constexpr TextStyle kStepCount{Font::Mono, 12.5f, 0, false, 1};
constexpr TextStyle kPercent{Font::DisplayBlackItalic, 132, -.02f, false, 1};
constexpr TextStyle kLog{Font::Mono, 12.5f, 0, false, 1.55f};
constexpr TextStyle kChip{Font::DisplayExtraBoldItalic, 13, .1f, true, 1};
constexpr TextStyle kSlot{Font::DisplayExtraBoldItalic, 12, .22f, true, 1};
constexpr TextStyle kPairCode{Font::DisplayBlackItalic, 58, -.01f, true, 1};
constexpr TextStyle kTagMark{Font::DisplayBlackItalic, 16, .08f, true, 1};
constexpr TextStyle kDialogTitle{Font::DisplayBlackItalic, 36, .02f, true, 1.02f};
constexpr TextStyle kFileName{Font::BodySemiBold, 14.5f, 0, false, 1};
constexpr TextStyle kFileMeta{Font::Mono, 12.5f, 0, false, 1};
constexpr TextStyle kWatermark{Font::DisplayBlackItalic, 300, -.02f, true, 1};
constexpr TextStyle kWindowTitle{Font::DisplayBoldItalic, 13, .14f, true, 1};
}  // namespace text

// ---- metrics of the widgets (points) -----------------------------------------------------------------------------
namespace metric {
constexpr float kSlabHeight = 112, kMenuRowHeight = 58, kMenuRowGap = 10, kMenuIconBox = 36;
constexpr float kTileWidth = 70, kTileHeight = 92, kTileGap = 8;
constexpr float kSettingRowHeight = 54, kSettingRowGap = 8, kValueBoxMin = 118, kValueBoxHeight = 32;
constexpr float kKeyRowHeight = 36, kStepRowHeight = 50, kFileRowHeight = 42, kPlaceRowHeight = 38;
constexpr float kButtonHeight = 46, kButtonSmallHeight = 38, kButtonTinyHeight = 28;
constexpr float kPillHeight = 24, kChipHeight = 26, kLabelHeight = 20, kSectionHeight = 44;
constexpr float kGlyphSize = 22;            // prompt glyphs (key caps, pad buttons)
constexpr float kProgressHeight = 30, kMiniBarHeight = 6;
constexpr float kFocusPad = 6;              // the focus highlight's distance around an item
constexpr float kScrollBarWidth = 4, kScrollBarGrab = 12;
constexpr float kWindowDragStrip = 76;      // the top band is the drag strip
constexpr float kResizeEdge = 6;
// The window's own minimise / fullscreen / close buttons: flush in the top-right corner, as Windows draws its own.
constexpr float kCaptionButtonWidth = 46, kCaptionButtonHeight = 34, kCaptionGlyph = 14;
constexpr float kCaptionButton = 46;        // minimise / fullscreen / close
}  // namespace metric

// ---- motion ------------------------------------------------------------------------------------------------------
struct SpringSpec {
    float stiffness;
    float ratio;  // damping ratio: 1 = critically damped
};
namespace motion {
constexpr SpringSpec kFocus{760, .8f};       // the focus highlight
constexpr SpringSpec kTabBar{600, .78f};     // the tab underline
constexpr SpringSpec kSeam{140, .86f};       // the split value C
constexpr SpringSpec kPlateBottom{140, .9f};
constexpr SpringSpec kLean{160, .75f};
constexpr SpringSpec kScroll{300, 1.f};      // scroll containers following the focus
constexpr SpringSpec kReduced{2600, 1.f};    // every spring when Reduce motion is on (snaps)
constexpr float kSpringStep = 1.f / 240;     // integration sub-step
constexpr float kBrightRate = 6;             // field brightness easing per second
constexpr float kBrightBlue = 1.3f, kBrightRed = 1.12f;
// The blue readout: the new content comes in from the right (the half's straight edge) and along the seam, the old
// one leaves to the right; neither ever moves toward the seam (FEEDBACK F1).
constexpr float kReadoutIn = .26f, kReadoutOut = .2f, kReadoutDx = 22, kReadoutDy = 12, kReadoutOutDx = 18;
// A drill-in lock (FEEDBACK F4): the locked half's content fades to this much and moves this far away from the
// seam, at this rate per second (eased); its plate darkens by kLockVeil.
constexpr float kLockOpacity = .42f, kLockPush = 10, kLockRate = 12, kLockVeil = .42f;
constexpr float kWipe = .4f, kWipeReduced = .14f;
constexpr float kBand = .32f, kScrimFade = .2f;
constexpr float kEntry = .42f, kEntryStagger = .04f;
constexpr float kGhost = .22f, kBump = 260;
constexpr float kProgressSmooth = 9;         // progress fill approach rate per second
constexpr float kAmbientHz = 30;             // the ambient layer is redrawn at most this often
constexpr float kAmbientIdlePause = 20;      // ... and pauses this long after the last input
constexpr float kHalftoneSpeed = 14, kHalftoneStep = 13, kHalftoneReach = 320, kHalftoneDot = 4.4f;
constexpr int kSpeedLines = 56;
constexpr float kSpeedLineReach = 560, kPulseSpeed = 420, kSparkRate = 26;
}  // namespace motion

// ---- input timing ------------------------------------------------------------------------------------------------
namespace input {
constexpr double kSamePress = .12;           // the same action from another device this soon counts once
constexpr double kKeyRepeatDelay = .4, kKeyRepeatRate = .08;
constexpr double kPadRepeatDelay = .38, kPadRepeatRate = .085;
constexpr float kStickPress = .5f, kStickRelease = .35f;  // dead zone with hysteresis
constexpr double kMouseAfterNav = .3;        // mouse motion ignored this long after pad/keyboard navigation
constexpr float kMouseHoverSlop = 4;         // ... and until it moved this far (points)
constexpr double kCaptureKeyboardIgnore = .25;  // capture started by a pad: keyboard ignored this long
constexpr double kPadPollInterval = 1.0 / 120;
constexpr double kPadInitDelay = .2;         // the gamepad subsystem starts this long after focus came
constexpr float kWheelStep = 64;             // points per wheel notch
}  // namespace input

}  // namespace ttt2::ui::theme
