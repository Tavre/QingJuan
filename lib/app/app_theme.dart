import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/foundation.dart';

/// v1.3.4 Windows 桌面端使用的青绿色 Fluent 强调色。
final qingJuanAccent = AccentColor.swatch(const <String, Color>{
  'darkest': Color(0xFF06433D),
  'darker': Color(0xFF075D55),
  'dark': Color(0xFF087269),
  'normal': Color(0xFF0B8278),
  'light': Color(0xFF339D94),
  'lighter': Color(0xFF72C2BB),
  'lightest': Color(0xFFD5EFEC),
});

/// Android 移动端自 v1.4 起使用的书卷暖色强调色。
final qingJuanMobileAccent = AccentColor.swatch(const <String, Color>{
  'darkest': Color(0xFF603323),
  'darker': Color(0xFF83432F),
  'dark': Color(0xFFA9553D),
  'normal': Color(0xFFD16D50),
  'light': Color(0xFFDE886D),
  'lighter': Color(0xFFEAB09C),
  'lightest': Color(0xFFF8E5DD),
});

const qingJuanWarmOrange = Color(0xFFD19A64);
const qingJuanCoral = Color(0xFFD16D50);
const qingJuanPaper = Color(0xFFF4F0E6);
const qingJuanPaperSurface = Color(0xFFFFFDF8);
const qingJuanInk = Color(0xFF1B1A18);
const qingJuanDarkSurface = Color(0xFF24231F);
const qingJuanDarkElevated = Color(0xFF2C2A25);

FluentThemeData buildQingJuanTheme(
  Brightness brightness, {
  TargetPlatform? platform,
}) {
  final target = platform ?? defaultTargetPlatform;
  return switch (target) {
    TargetPlatform.android ||
    TargetPlatform.iOS ||
    TargetPlatform.fuchsia =>
      _buildMobileTheme(brightness),
    TargetPlatform.windows ||
    TargetPlatform.macOS ||
    TargetPlatform.linux =>
      _buildDesktopTheme(brightness),
  };
}

FluentThemeData _buildDesktopTheme(Brightness brightness) {
  final isDark = brightness == Brightness.dark;
  return FluentThemeData(
    brightness: brightness,
    accentColor: qingJuanAccent,
    fasterAnimationDuration: const Duration(milliseconds: 60),
    fastAnimationDuration: const Duration(milliseconds: 110),
    mediumAnimationDuration: const Duration(milliseconds: 170),
    slowAnimationDuration: const Duration(milliseconds: 240),
    animationCurve: Curves.easeOutCubic,
    visualDensity: VisualDensity.standard,
    fontFamily: 'Segoe UI Variable Text',
    scaffoldBackgroundColor:
        isDark ? const Color(0xFF202020) : const Color(0xFFF3F3F3),
    micaBackgroundColor:
        isDark ? const Color(0xFF202020) : const Color(0xFFF3F3F3),
    acrylicBackgroundColor:
        isDark ? const Color(0xFF2B2B2B) : const Color(0xFFF9F9F9),
    menuColor: isDark ? const Color(0xFF2C2C2C) : const Color(0xFFFAFAFA),
    inactiveBackgroundColor:
        isDark ? const Color(0xFF303030) : const Color(0xFFEAEAEA),
    cardColor: isDark ? const Color(0xFF292929) : const Color(0xFFFBFBFB),
    navigationPaneTheme: NavigationPaneThemeData(
      animationDuration: const Duration(milliseconds: 110),
      animationCurve: Curves.easeOutCubic,
      backgroundColor:
          isDark ? const Color(0xFF202020) : const Color(0xFFF7F7F7),
      overlayBackgroundColor:
          isDark ? const Color(0xFF252525) : const Color(0xFFFAFAFA),
      headerPadding: const EdgeInsetsDirectional.only(
        start: 12,
        top: 14,
        end: 12,
        bottom: 6,
      ),
      iconPadding: const EdgeInsets.symmetric(horizontal: 12),
      labelPadding: const EdgeInsetsDirectional.only(end: 12),
    ),
    typography: Typography.raw(
      caption: TextStyle(
        fontFamily: 'Segoe UI Variable Text',
        fontSize: 12,
        color: isDark ? const Color(0xFFC7C7C7) : const Color(0xFF5D5D5D),
      ),
      body: TextStyle(
        fontFamily: 'Segoe UI Variable Text',
        fontSize: 14,
        color: isDark ? const Color(0xFFF2F2F2) : const Color(0xFF1B1B1B),
      ),
      bodyLarge: TextStyle(
        fontFamily: 'Segoe UI Variable Text',
        fontSize: 16,
        color: isDark ? const Color(0xFFF5F5F5) : const Color(0xFF171717),
      ),
      subtitle: TextStyle(
        fontFamily: 'Segoe UI Variable Display',
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFF5F5F5) : const Color(0xFF171717),
      ),
      title: TextStyle(
        fontFamily: 'Segoe UI Variable Display',
        fontSize: 28,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFFFFFFF) : const Color(0xFF111111),
      ),
      titleLarge: TextStyle(
        fontFamily: 'Segoe UI Variable Display',
        fontSize: 32,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFFFFFFF) : const Color(0xFF111111),
      ),
      display: TextStyle(
        fontFamily: 'Segoe UI Variable Display',
        fontSize: 42,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFFFFFFF) : const Color(0xFF111111),
      ),
    ),
  );
}

FluentThemeData _buildMobileTheme(Brightness brightness) {
  final isDark = brightness == Brightness.dark;
  return FluentThemeData(
    brightness: brightness,
    accentColor: qingJuanMobileAccent,
    fasterAnimationDuration: const Duration(milliseconds: 60),
    fastAnimationDuration: const Duration(milliseconds: 110),
    mediumAnimationDuration: const Duration(milliseconds: 170),
    slowAnimationDuration: const Duration(milliseconds: 240),
    animationCurve: Curves.easeOutCubic,
    visualDensity: VisualDensity.standard,
    scaffoldBackgroundColor: isDark ? qingJuanInk : qingJuanPaper,
    micaBackgroundColor: isDark ? qingJuanInk : qingJuanPaper,
    acrylicBackgroundColor:
        isDark ? qingJuanDarkElevated : const Color(0xFFFCF8EF),
    menuColor: isDark ? qingJuanDarkElevated : const Color(0xFFFCF8EF),
    inactiveBackgroundColor:
        isDark ? const Color(0xFF34312B) : const Color(0xFFE8E1D4),
    cardColor: isDark ? qingJuanDarkSurface : qingJuanPaperSurface,
    navigationPaneTheme: NavigationPaneThemeData(
      animationDuration: const Duration(milliseconds: 110),
      animationCurve: Curves.easeOutCubic,
      backgroundColor: isDark ? qingJuanInk : qingJuanPaper,
      overlayBackgroundColor:
          isDark ? qingJuanDarkElevated : const Color(0xFFFCF8EF),
      headerPadding: const EdgeInsetsDirectional.only(
        start: 12,
        top: 14,
        end: 12,
        bottom: 6,
      ),
      iconPadding: const EdgeInsets.symmetric(horizontal: 12),
      labelPadding: const EdgeInsetsDirectional.only(end: 12),
    ),
    typography: Typography.raw(
      caption: TextStyle(
        fontSize: 12,
        color: isDark ? const Color(0xFFBDB6AA) : const Color(0xFF726B62),
      ),
      body: TextStyle(
        fontSize: 14,
        color: isDark ? const Color(0xFFF0ECE4) : const Color(0xFF35312C),
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        color: isDark ? const Color(0xFFF4F0E8) : const Color(0xFF302C27),
      ),
      subtitle: TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFF5F1E9) : const Color(0xFF2D2925),
      ),
      title: TextStyle(
        fontSize: 28,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFF8F5EE) : const Color(0xFF292621),
      ),
      titleLarge: TextStyle(
        fontSize: 34,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFF8F5EE) : const Color(0xFF292621),
      ),
      display: TextStyle(
        fontSize: 42,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFF8F5EE) : const Color(0xFF292621),
      ),
    ),
  );
}
