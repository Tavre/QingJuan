import 'package:fluent_ui/fluent_ui.dart';

final qingJuanAccent = AccentColor.swatch(const <String, Color>{
  'darkest': Color(0xFF06433D),
  'darker': Color(0xFF075D55),
  'dark': Color(0xFF087269),
  'normal': Color(0xFF0B8278),
  'light': Color(0xFF339D94),
  'lighter': Color(0xFF72C2BB),
  'lightest': Color(0xFFD5EFEC),
});

FluentThemeData buildQingJuanTheme(Brightness brightness) {
  final isDark = brightness == Brightness.dark;
  return FluentThemeData(
    brightness: brightness,
    accentColor: qingJuanAccent,
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
