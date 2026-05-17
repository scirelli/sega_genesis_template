#!/usr/bin/env python3
"""
asm68k_to_vasm — Convert asm68k (SN 68K Assembler) source files to vasm mot syntax.

This is a proper parser-based converter, not a regex hack. It handles:
- `!` as bitwise OR → `|`
- `@LABEL` local labels → `.LABEL`
- `INCLUDE file` → `INCLUDE "file"` (quotes required by vasm)
- `INCBIN file` → `INCBIN "file"`
- Preserves \\@ macro unique suffixes (not local labels)
- Preserves \\1, \\2 etc macro arguments
- Preserves formatting, comments, and blank lines

Usage:
    python3 asm68k_to_vasm.py <input> [-o <output>]
    python3 asm68k_to_vasm.py <directory> [-o <directory>]
    python3 asm68k_to_vasm.py --map-flags "<asm68k flags>"
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# =============================================================================
# Token Types
# =============================================================================

class TokenType(Enum):
    LABEL = auto()
    LOCAL_LABEL = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    CHAR_LITERAL = auto()
    OPERATOR = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    COMMENT = auto()
    WHITESPACE = auto()
    NEWLINE = auto()
    MACRO_ARG = auto()
    MACRO_UNIQUE = auto()
    DOT = auto()
    COLON = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    pos: int


# =============================================================================
# Lexer
# =============================================================================

class Lexer:
    """Tokenizes a single line of asm68k source."""

    OPERATORS = set('+-*/!&|~<>^#')

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.tokens: list[Token] = []

    def peek(self) -> str:
        if self.pos < len(self.text):
            return self.text[self.pos]
        return ''

    def advance(self) -> str:
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def tokenize(self) -> list[Token]:
        while not self.at_end():
            start = self.pos
            ch = self.peek()

            if ch == ';':
                self.tokens.append(Token(TokenType.COMMENT, self.text[self.pos:], start))
                self.pos = len(self.text)

            elif ch == '*' and start == 0:
                self.tokens.append(Token(TokenType.COMMENT, self.text[self.pos:], start))
                self.pos = len(self.text)

            elif ch in (' ', '\t'):
                self._read_whitespace(start)

            elif ch == '\\':
                self._read_backslash_sequence(start)

            elif ch == '@':
                self._read_at_label(start)

            elif ch == '$':
                self._read_hex_number(start)

            elif ch == '%':
                self._read_binary_number(start)

            elif ch.isdigit():
                self._read_decimal_number(start)

            elif ch == '"' or ch == "'":
                self._read_string(start, ch)

            elif ch == '(':
                self.advance()
                self.tokens.append(Token(TokenType.LPAREN, '(', start))

            elif ch == ')':
                self.advance()
                self.tokens.append(Token(TokenType.RPAREN, ')', start))

            elif ch == ',':
                self.advance()
                self.tokens.append(Token(TokenType.COMMA, ',', start))

            elif ch == '.':
                self.advance()
                self.tokens.append(Token(TokenType.DOT, '.', start))

            elif ch == ':':
                self.advance()
                self.tokens.append(Token(TokenType.COLON, ':', start))

            elif ch == '<' and self.pos + 1 < len(self.text) and self.text[self.pos + 1] == '<':
                self.pos += 2
                self.tokens.append(Token(TokenType.OPERATOR, '<<', start))

            elif ch == '>' and self.pos + 1 < len(self.text) and self.text[self.pos + 1] == '>':
                self.pos += 2
                self.tokens.append(Token(TokenType.OPERATOR, '>>', start))

            elif ch in self.OPERATORS:
                self.advance()
                self.tokens.append(Token(TokenType.OPERATOR, ch, start))

            elif ch.isalpha() or ch == '_':
                self._read_identifier(start)

            else:
                self.advance()
                self.tokens.append(Token(TokenType.OPERATOR, ch, start))

        return self.tokens

    def _read_whitespace(self, start: int):
        while not self.at_end() and self.peek() in (' ', '\t'):
            self.advance()
        self.tokens.append(Token(TokenType.WHITESPACE, self.text[start:self.pos], start))

    def _read_backslash_sequence(self, start: int):
        self.advance()  # consume '\'
        if self.at_end():
            self.tokens.append(Token(TokenType.OPERATOR, '\\', start))
            return
        ch = self.peek()
        if ch == '@':
            self.advance()
            self.tokens.append(Token(TokenType.MACRO_UNIQUE, '\\@', start))
        elif ch.isdigit():
            self.advance()
            self.tokens.append(Token(TokenType.MACRO_ARG, '\\' + ch, start))
        else:
            self.tokens.append(Token(TokenType.OPERATOR, '\\', start))

    def _read_at_label(self, start: int):
        self.advance()  # consume '@'
        label_start = self.pos
        while not self.at_end() and (self.peek().isalnum() or self.peek() == '_'):
            self.advance()
        name = self.text[label_start:self.pos]
        if name:
            self.tokens.append(Token(TokenType.LOCAL_LABEL, '@' + name, start))
        else:
            self.tokens.append(Token(TokenType.OPERATOR, '@', start))

    def _read_hex_number(self, start: int):
        self.advance()  # consume '$'
        while not self.at_end() and self.peek() in '0123456789ABCDEFabcdef':
            self.advance()
        self.tokens.append(Token(TokenType.NUMBER, self.text[start:self.pos], start))

    def _read_binary_number(self, start: int):
        self.advance()  # consume '%'
        while not self.at_end() and self.peek() in '01':
            self.advance()
        if self.pos > start + 1:
            self.tokens.append(Token(TokenType.NUMBER, self.text[start:self.pos], start))
        else:
            self.tokens.append(Token(TokenType.OPERATOR, '%', start))

    def _read_decimal_number(self, start: int):
        while not self.at_end() and self.peek().isdigit():
            self.advance()
        self.tokens.append(Token(TokenType.NUMBER, self.text[start:self.pos], start))

    def _read_string(self, start: int, quote: str):
        self.advance()  # consume opening quote
        while not self.at_end() and self.peek() != quote:
            if self.peek() == '\\':
                self.advance()
                if not self.at_end():
                    self.advance()
            else:
                self.advance()
        if not self.at_end():
            self.advance()  # consume closing quote
        self.tokens.append(Token(TokenType.STRING, self.text[start:self.pos], start))

    def _read_identifier(self, start: int):
        while not self.at_end() and (self.peek().isalnum() or self.peek() == '_'):
            self.advance()
        self.tokens.append(Token(TokenType.IDENTIFIER, self.text[start:self.pos], start))


# =============================================================================
# AST Node Types
# =============================================================================

@dataclass
class ASTNode:
    pass


@dataclass
class BlankLine(ASTNode):
    pass


@dataclass
class CommentLine(ASTNode):
    text: str
    leading_whitespace: str = ''


@dataclass
class Expression(ASTNode):
    tokens: list[Token] = field(default_factory=list)


@dataclass
class Operand(ASTNode):
    tokens: list[Token] = field(default_factory=list)


@dataclass
class SourceLine(ASTNode):
    """Represents a single line of assembly source."""
    label: Optional[str] = None
    label_is_local: bool = False
    label_suffix: str = ''  # ':' or whitespace after label
    opcode: Optional[str] = None
    opcode_size: Optional[str] = None  # .B, .W, .L, etc.
    operands_raw: str = ''  # raw operand text for transformation
    comment: Optional[str] = None
    # Formatting preservation
    pre_label_ws: str = ''
    post_label_ws: str = ''
    pre_opcode_ws: str = ''
    post_opcode_ws: str = ''
    pre_comment_ws: str = ''
    raw_line: str = ''  # original full line for fallback


# =============================================================================
# Parser
# =============================================================================

class Parser:
    """Parses tokenized lines into AST nodes."""

    DIRECTIVES = {
        'EQU', 'SET', 'ORG', 'DC', 'DS', 'DCB', 'EVEN', 'ODD', 'ALIGN',
        'INCLUDE', 'INCBIN', 'INCDIR',
        'MACRO', 'ENDM', 'MEXIT',
        'REPT', 'ENDR',
        'IF', 'IFD', 'IFND', 'IFEQ', 'IFNE', 'IFGT', 'IFGE', 'IFLT', 'IFLE',
        'ELSE', 'ELSEIF', 'ENDIF', 'ENDC',
        'RSSET', 'RSRESET', 'RS',
        'SECTION', 'END', 'NARG', 'FAIL', 'INFORM',
        'OPT', 'LIST', 'NOLIST', 'PAGE', 'NOPAGE',
        'CNOP', 'OFFSET', 'PUSHOFFSET', 'PULOFFSET',
    }

    SIZE_SUFFIXES = {'B', 'W', 'L', 'S'}

    def parse_line(self, raw_line: str) -> ASTNode:
        """Parse a single source line into an AST node."""
        if not raw_line or raw_line.isspace():
            return BlankLine()

        # Full-line comment
        stripped = raw_line.lstrip()
        if stripped.startswith(';') or (stripped.startswith('*') and not stripped[1:2].isalnum()):
            leading_ws = raw_line[:len(raw_line) - len(stripped)]
            return CommentLine(text=stripped, leading_whitespace=leading_ws)

        return self._parse_instruction_line(raw_line)

    def _parse_instruction_line(self, raw_line: str) -> SourceLine:
        node = SourceLine(raw_line=raw_line)
        text = raw_line
        pos = 0

        # Check for label (starts at column 0, no leading whitespace)
        if text and text[0] not in (' ', '\t', ';', '*'):
            pos = self._extract_label(text, pos, node)

        # Skip whitespace to opcode
        ws_start = pos
        while pos < len(text) and text[pos] in (' ', '\t'):
            pos += 1
        node.pre_opcode_ws = text[ws_start:pos]

        if pos >= len(text) or text[pos] == ';':
            if pos < len(text):
                node.comment = text[pos:]
            return node

        # Extract opcode (possibly with size suffix)
        opcode_start = pos
        while pos < len(text) and text[pos] not in (' ', '\t', ';', '.'):
            pos += 1

        if pos < len(text) and text[pos] == '.':
            # Size suffix
            dot_pos = pos
            pos += 1
            size_start = pos
            while pos < len(text) and text[pos].isalpha():
                pos += 1
            node.opcode = text[opcode_start:dot_pos]
            node.opcode_size = text[dot_pos:pos]
        else:
            node.opcode = text[opcode_start:pos]

        # Skip whitespace to operands
        ws_start = pos
        while pos < len(text) and text[pos] in (' ', '\t'):
            pos += 1
        node.post_opcode_ws = text[ws_start:pos]

        # Extract operands (everything up to comment)
        if pos < len(text) and text[pos] != ';':
            operand_start = pos
            # Find comment (semicolon not inside quotes)
            in_quotes = False
            quote_char = None
            while pos < len(text):
                ch = text[pos]
                if in_quotes:
                    if ch == quote_char:
                        in_quotes = False
                    elif ch == '\\':
                        pos += 1
                elif ch in ('"', "'"):
                    in_quotes = True
                    quote_char = ch
                elif ch == ';':
                    break
                pos += 1

            # Trim trailing whitespace from operands, capture as pre-comment ws
            operand_end = pos
            while operand_end > operand_start and text[operand_end - 1] in (' ', '\t'):
                operand_end -= 1
            node.operands_raw = text[operand_start:operand_end]
            node.pre_comment_ws = text[operand_end:pos]

        # Comment
        if pos < len(text) and text[pos] == ';':
            node.comment = text[pos:]

        return node

    def _extract_label(self, text: str, pos: int, node: SourceLine) -> int:
        """Extract a label starting at pos. Returns new position."""
        if text[pos] == '@':
            # Local label
            node.label_is_local = True
            pos += 1
            label_start = pos
            while pos < len(text) and (text[pos].isalnum() or text[pos] == '_'):
                pos += 1
            node.label = '@' + text[label_start:pos]
        else:
            # Global label
            label_start = pos
            while pos < len(text) and (text[pos].isalnum() or text[pos] == '_'):
                pos += 1
            node.label = text[label_start:pos]

        # Check for colon after label
        if pos < len(text) and text[pos] == ':':
            node.label_suffix = ':'
            pos += 1

        return pos


# =============================================================================
# Transformer
# =============================================================================

class Transformer:
    """Transforms AST nodes from asm68k to vasm syntax."""

    INCLUDE_DIRECTIVES = {'INCLUDE', 'INCBIN'}

    def transform(self, node: ASTNode) -> ASTNode:
        if isinstance(node, SourceLine):
            return self._transform_source_line(node)
        return node

    def _transform_source_line(self, node: SourceLine) -> SourceLine:
        # Transform local label
        if node.label_is_local and node.label and node.label.startswith('@'):
            node.label = '.' + node.label[1:]

        # Transform operands
        if node.operands_raw:
            # Transform INCLUDE/INCBIN to add quotes
            if node.opcode and node.opcode.upper() in self.INCLUDE_DIRECTIVES:
                node.operands_raw = self._add_quotes_if_missing(node.operands_raw)
            else:
                node.operands_raw = self._transform_operands(node.operands_raw)

        return node

    def _add_quotes_if_missing(self, operands: str) -> str:
        """Add quotes around include path if not already quoted."""
        stripped = operands.strip()
        if stripped.startswith('"') or stripped.startswith("'"):
            return operands
        return '"' + operands + '"'

    def _transform_operands(self, operands: str) -> str:
        """Transform operand expressions: ! → |, @label → .label"""
        result = []
        i = 0
        in_string = False
        quote_char = None

        while i < len(operands):
            ch = operands[i]

            # Track string context
            if in_string:
                result.append(ch)
                if ch == quote_char:
                    in_string = False
                elif ch == '\\' and i + 1 < len(operands):
                    i += 1
                    result.append(operands[i])
                i += 1
                continue

            if ch in ('"', "'"):
                in_string = True
                quote_char = ch
                result.append(ch)
                i += 1
                continue

            # Transform \@ — preserve as-is (macro unique suffix)
            if ch == '\\' and i + 1 < len(operands):
                next_ch = operands[i + 1]
                if next_ch == '@' or next_ch.isdigit():
                    result.append(ch)
                    result.append(next_ch)
                    i += 2
                    continue
                result.append(ch)
                i += 1
                continue

            # Transform ! → | (bitwise OR)
            if ch == '!':
                result.append('|')
                i += 1
                continue

            # Transform @LABEL → .LABEL (local label reference)
            if ch == '@':
                # Check if followed by identifier chars (it's a local label ref)
                if i + 1 < len(operands) and (operands[i + 1].isalpha() or operands[i + 1] == '_'):
                    result.append('.')
                    i += 1
                    # Consume the label name
                    while i < len(operands) and (operands[i].isalnum() or operands[i] == '_'):
                        result.append(operands[i])
                        i += 1
                    continue
                else:
                    result.append(ch)
                    i += 1
                    continue

            result.append(ch)
            i += 1

        return ''.join(result)


# =============================================================================
# Emitter
# =============================================================================

class Emitter:
    """Emits transformed AST nodes back to source text."""

    def emit(self, node: ASTNode) -> str:
        if isinstance(node, BlankLine):
            return ''
        elif isinstance(node, CommentLine):
            return node.leading_whitespace + node.text
        elif isinstance(node, SourceLine):
            return self._emit_source_line(node)
        return ''

    def _emit_source_line(self, node: SourceLine) -> str:
        parts = []

        # Label
        if node.label:
            parts.append(node.label)
            parts.append(node.label_suffix)

        # Whitespace before opcode
        parts.append(node.pre_opcode_ws)

        # Opcode with size
        if node.opcode:
            parts.append(node.opcode)
            if node.opcode_size:
                parts.append(node.opcode_size)

        # Whitespace after opcode
        parts.append(node.post_opcode_ws)

        # Operands
        if node.operands_raw:
            parts.append(node.operands_raw)

        # Pre-comment whitespace and comment
        if node.comment:
            parts.append(node.pre_comment_ws)
            parts.append(node.comment)

        return ''.join(parts)


# =============================================================================
# Converter (orchestrates the pipeline)
# =============================================================================

class Converter:
    """Orchestrates the full conversion pipeline."""

    def __init__(self):
        self.parser = Parser()
        self.transformer = Transformer()
        self.emitter = Emitter()

    def convert_line(self, line: str) -> str:
        """Convert a single line of source."""
        # Strip trailing newline for processing, re-add later
        stripped = line.rstrip('\n').rstrip('\r')
        node = self.parser.parse_line(stripped)
        node = self.transformer.transform(node)
        return self.emitter.emit(node)

    def convert_file(self, input_path: str, output_path: str):
        """Convert an entire file. Normalizes line endings to LF."""
        with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        converted = []
        for line in lines:
            converted_line = self.convert_line(line)
            converted.append(converted_line)

        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            for i, line in enumerate(converted):
                f.write(line)
                if i < len(lines) - 1:
                    f.write('\n')
                elif lines[-1].endswith('\n'):
                    f.write('\n')

    def convert_directory(self, input_dir: str, output_dir: str):
        """Convert all .s and .asm files in a directory."""
        os.makedirs(output_dir, exist_ok=True)
        extensions = ('.s', '.asm', '.68k')
        for filename in os.listdir(input_dir):
            if any(filename.lower().endswith(ext) for ext in extensions):
                input_path = os.path.join(input_dir, filename)
                output_path = os.path.join(output_dir, filename)
                print(f"Converting: {input_path} → {output_path}")
                self.convert_file(input_path, output_path)


# =============================================================================
# Flag Mapper
# =============================================================================

FLAG_MAP = {
    '/p': None,  # progress display — no vasm equivalent
    '/o': None,  # output file — handled differently in vasm
    '/ov+': '-opt-allbra',
    '/ov-': None,
    '/oos+': '-opt-speed',
    '/oos-': None,
    '/oop+': '-opt-allbra',
    '/oop-': None,
    '/oow+': '-opt-lsl',
    '/oow-': None,
    '/ooz+': '-opt-allbra',
    '/ooz-': None,
    '/ooaq+': '-opt-pea',
    '/ooaq-': None,
    '/oosq+': '-opt-lsl',
    '/oosq-': None,
    '/oomq+': '-opt-movem',
    '/oomq-': None,
    '/ow+': None,  # warnings — vasm enables by default
    '/ow-': '-nowarn=62',
    '/e': None,  # error file
    '/l': None,  # listing file — use -L in vasm
    '/d': None,  # define symbol
}


def map_flags(asm68k_flags: str) -> str:
    """Map asm68k command-line flags to vasm equivalents."""
    vasm_flags = ['-Fbin', '-m68000']
    tokens = asm68k_flags.split()

    i = 0
    while i < len(tokens):
        flag = tokens[i]

        # /j path — include path
        if flag.lower() == '/j' and i + 1 < len(tokens):
            path = tokens[i + 1]
            path = path.replace('\\*', '')
            if path.endswith('/') or path.endswith('\\'):
                pass
            vasm_flags.append(f'-I {path}')
            i += 2
            continue

        # Lookup in map
        mapped = FLAG_MAP.get(flag.lower())
        if mapped:
            if mapped not in vasm_flags:
                vasm_flags.append(mapped)
        elif flag.lower() not in FLAG_MAP:
            vasm_flags.append(f'# unknown: {flag}')

        i += 1

    return ' '.join(vasm_flags)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Convert asm68k source files to vasm (mot syntax)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('input', nargs='?', help='Input file or directory')
    parser.add_argument('-o', '--output', help='Output file or directory (default: stdout)')
    parser.add_argument('--map-flags', metavar='FLAGS',
                        help='Map asm68k flags to vasm equivalents')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be changed without writing')

    args = parser.parse_args()

    if args.map_flags:
        result = map_flags(args.map_flags)
        print(f"vasm flags: {result}")
        return

    if not args.input:
        parser.error("input file or directory required (unless using --map-flags)")

    converter = Converter()

    if os.path.isdir(args.input):
        output_dir = args.output if args.output else args.input
        converter.convert_directory(args.input, output_dir)
    elif os.path.isfile(args.input):
        if args.dry_run:
            with open(args.input, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            for i, line in enumerate(lines, 1):
                original = line.rstrip('\n')
                converted = converter.convert_line(line)
                if original != converted:
                    print(f"L{i}: {original}")
                    print(f"  → {converted}")
        elif args.output:
            converter.convert_file(args.input, args.output)
            print(f"Converted: {args.input} → {args.output}")
        else:
            with open(args.input, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    print(converter.convert_line(line))
    else:
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
