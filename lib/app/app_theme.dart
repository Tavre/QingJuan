import 'package:fluent_ui/fluent_ui.dart';

final qingJuanAccent = AccentColor.swatch(const <String, Color>{
  'darkest': Color(0xFF064E47),
  'darker': Color(0xFF076A60),
  'dark': Color(0xFF087C70),
  'normal': Color(0xFF0A8F81),
  'light': Color(0xFF36A99D),
  'lighter': Color(0xFF75C7BE),
  'lightest': Color(0xFFCBEAE6),
});

FluentThemeData buildQingJuanTheme(Brightness brightness) {
  final isDark = brightness == Brightness.dark;
  return FluentThemeData(
    brightness: brightness,
    accentColor: qingJuanAccent,
    visualDensity: VisualDensity.standard,
    scaffoldBackgroundColor:
        isDark ? const Color(0xFF171A19) : const Color(0xFFF5F7F6),
    inactiveBackgroundColor:
        isDark ? const Color(0xFF232826) : const Color(0xFFEDF2F0),
    cardColor: isDark ? const Color(0xFF202523) : const Color(0xFFFBFCFB),
    typography: Typography.raw(
      caption: TextStyle(
        fontFamily: 'Segoe UI',
        fontSize: 12,
        color: isDark ? const Color(0xFFB7C1BD) : const Color(0xFF58625F),
      ),
      body: TextStyle(
        fontFamily: 'Segoe UI',
        fontSize: 14,
        color: isDark ? const Color(0xFFE8EEEB) : const Color(0xFF202724),
      ),
      bodyLarge: TextStyle(
        fontFamily: 'Segoe UI',
        fontSize: 16,
        color: isDark ? const Color(0xFFF0F4F2) : const Color(0xFF17201D),
      ),
      subtitle: TextStyle(
        fontFamily: 'Segoe UI',
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: isDark ? const Color(0xFFF0F4F2) : const Color(0xFF17201D),
      ),
      title: TextStyle(
        fontFamily: 'Segoe UI',
        fontSize: 28,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFF7FAF8) : const Color(0xFF101714),
      ),
      titleLarge: TextStyle(
        fontFamily: 'Segoe UI',
        fontSize: 36,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFF7FAF8) : const Color(0xFF101714),
      ),
      display: TextStyle(
        fontFamily: 'Segoe UI',
        fontSize: 48,
        fontWeight: FontWeight.w700,
        color: isDark ? const Color(0xFFF7FAF8) : const Color(0xFF101714),
      ),
    ),
  );
}
