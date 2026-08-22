import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/material.dart' as material;
import 'package:flutter_miuix/miuix.dart' as miuix;

import '../app/app_theme.dart';

/// Bridges the app's persisted light/dark choice into flutter_miuix.
///
/// The desktop subtree keeps using Fluent UI. Only the mobile shell installs
/// this theme, so secondary routes can continue to share the existing data and
/// navigation layers without changing the Windows visual language.
class QingJuanMiuixTheme extends StatelessWidget {
  const QingJuanMiuixTheme({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final brightness = FluentTheme.of(context).brightness;
    return miuix.MiuixThemeController(
      colorSchemeMode: brightness == Brightness.dark
          ? miuix.MiuixColorSchemeMode.monetDark
          : miuix.MiuixColorSchemeMode.monetLight,
      keyColor: qingJuanMobileBlue,
      child: Builder(
        builder: (context) {
          final theme = miuix.MiuixTheme.of(context);
          return material.Theme(
            data: material.ThemeData(
              useMaterial3: true,
              brightness: theme.brightness,
              colorScheme: material.ColorScheme.fromSeed(
                seedColor: theme.colors.primary,
                brightness: theme.brightness,
              ),
              scaffoldBackgroundColor: theme.colors.background,
            ),
            child: material.Material(
              color: theme.colors.background,
              child: child,
            ),
          );
        },
      ),
    );
  }
}

class MobileMiuixButton extends StatelessWidget {
  const MobileMiuixButton({
    required this.onPressed,
    required this.child,
    this.primary = false,
    this.expand = false,
    this.minHeight = 40,
    this.keyName,
    super.key,
  });

  final VoidCallback? onPressed;
  final Widget child;
  final bool primary;
  final bool expand;
  final double minHeight;
  final String? keyName;

  @override
  Widget build(BuildContext context) {
    final button = miuix.MiuixButton(
      key: keyName == null ? null : ValueKey<String>(keyName!),
      onPressed: onPressed,
      minHeight: minHeight,
      colors: primary
          ? miuix.MiuixButtonDefaults.buttonColorsPrimary(context)
          : null,
      child: child,
    );
    return expand ? SizedBox(width: double.infinity, child: button) : button;
  }
}

class MobileMiuixIconButton extends StatelessWidget {
  const MobileMiuixIconButton({
    required this.icon,
    required this.label,
    required this.onPressed,
    this.backgroundColor,
    this.keyName,
    super.key,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onPressed;
  final Color? backgroundColor;
  final String? keyName;

  @override
  Widget build(BuildContext context) {
    final colors = miuix.MiuixTheme.of(context).colors;
    return Semantics(
      label: label,
      button: true,
      child: miuix.MiuixIconButton(
        key: keyName == null ? null : ValueKey<String>(keyName!),
        onPressed: onPressed,
        backgroundColor: backgroundColor,
        child: Icon(
          icon,
          size: 20,
          color: onPressed == null
              ? colors.disabledOnSurface
              : colors.onSurfaceVariantActions,
          semanticLabel: label,
        ),
      ),
    );
  }
}

class MobileMiuixSearchField extends StatelessWidget {
  const MobileMiuixSearchField({
    required this.placeholder,
    required this.onChanged,
    this.controller,
    this.onSubmitted,
    this.trailing,
    this.autofocus = false,
    super.key,
  });

  final TextEditingController? controller;
  final String placeholder;
  final ValueChanged<String> onChanged;
  final ValueChanged<String>? onSubmitted;
  final Widget? trailing;
  final bool autofocus;

  @override
  Widget build(BuildContext context) {
    final colors = miuix.MiuixTheme.of(context).colors;
    return material.Material(
      type: material.MaterialType.transparency,
      child: miuix.MiuixTextField(
        controller: controller,
        label: placeholder,
        useLabelAsPlaceholder: true,
        singleLine: true,
        autofocus: autofocus,
        textInputAction: TextInputAction.search,
        onChanged: onChanged,
        onSubmitted: onSubmitted,
        leadingIcon: Icon(
          FluentIcons.search,
          size: 19,
          color: colors.onSurfaceVariantActions,
        ),
        trailingIcon: trailing,
      ),
    );
  }
}
