import 'dart:math' as math;

import 'package:flutter/widgets.dart';

int estimateReaderPageCharacters(Size viewport, double fontSize) {
  final usableWidth = math.max(120.0, viewport.width - 48);
  final usableHeight = math.max(180.0, viewport.height - 170);
  final charactersPerLine = math.max(10, (usableWidth / fontSize).floor());
  final linesPerPage = math.max(6, (usableHeight / (fontSize * 1.85)).floor());
  return math.max(80, (charactersPerLine * linesPerPage * 0.9).floor());
}

List<String> paginateReaderText(String text, int targetCharacters) {
  if (text.isEmpty) return const <String>[''];
  final target = math.max(40, targetCharacters);
  final pages = <String>[];
  var start = 0;
  while (start < text.length) {
    var end = math.min(text.length, start + target);
    if (end < text.length) {
      final searchStart = math.min(end, start + (target * 0.72).floor());
      for (var index = end - 1; index >= searchStart; index--) {
        if (_isBreakCharacter(text.codeUnitAt(index))) {
          end = index + 1;
          break;
        }
      }
    }
    pages.add(text.substring(start, end));
    start = end;
  }
  return pages;
}

bool _isBreakCharacter(int codeUnit) =>
    codeUnit == 0x0A ||
    codeUnit == 0x3002 ||
    codeUnit == 0xFF01 ||
    codeUnit == 0xFF1F ||
    codeUnit == 0xFF1B ||
    codeUnit == 0xFF0C;
