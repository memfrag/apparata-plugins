#!/usr/bin/env python3
"""
Bootstrapp Template Engine & Instantiation Pipeline

A self-contained Python reimplementation of the Bootstrapp template system
(originally three Swift packages: TemplateKit, BootstrappKit, Bootstrapp app).

Parses Bootstrapp.json specs, renders template files using <{ }> tag syntax,
and optionally generates Xcode projects via the xcodegen CLI.

Usage:
    python3 bootstrapp.py <template-dir> [options]

Options:
    --param KEY=VALUE       Set a parameter value (repeatable)
    --exclude-package NAME  Exclude a spec-defined package (repeatable)
    --output-dir DIR        Override output directory
    --verbose               Print progress to stderr
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional


# =============================================================================
# Scanner Utility
# =============================================================================

class Scanner:
    """Position-based string scanner mimicking Foundation's Scanner."""

    def __init__(self, string: str):
        self.string = string
        self.pos = 0

    @property
    def is_at_end(self) -> bool:
        return self.pos >= len(self.string)

    @property
    def current_char(self) -> Optional[str]:
        if self.is_at_end:
            return None
        return self.string[self.pos]

    def scan_string(self, s: str) -> Optional[str]:
        if self.string[self.pos:self.pos + len(s)] == s:
            self.pos += len(s)
            return s
        return None

    def scan_up_to_string(self, s: str) -> Optional[str]:
        idx = self.string.find(s, self.pos)
        if idx == -1:
            return None
        result = self.string[self.pos:idx]
        self.pos = idx
        return result

    def scan_characters_from(self, charset: set) -> Optional[str]:
        start = self.pos
        while self.pos < len(self.string) and self.string[self.pos] in charset:
            self.pos += 1
        if self.pos == start:
            return None
        return self.string[start:self.pos]

    def scan_up_to_characters_from(self, charset: set) -> Optional[str]:
        start = self.pos
        while self.pos < len(self.string) and self.string[self.pos] not in charset:
            self.pos += 1
        if self.pos == start:
            return None
        return self.string[start:self.pos]

    def scan_character(self) -> Optional[str]:
        if self.is_at_end:
            return None
        ch = self.string[self.pos]
        self.pos += 1
        return ch

    def scan_whitespace(self) -> Optional[str]:
        return self.scan_characters_from(set(" \t\n\r"))

    def scan_identifier(self) -> Optional[str]:
        start = self.pos
        while self.pos < len(self.string) and (self.string[self.pos].isalnum() or self.string[self.pos] == '_'):
            self.pos += 1
        if self.pos == start:
            return None
        return self.string[start:self.pos]

    def scan_path(self) -> Optional[list]:
        path = []
        while True:
            ident = self.scan_identifier()
            if ident is None:
                break
            path.append(ident)
            backtrack = self.pos
            if self.scan_string('.') is None:
                break
            # Check if dot is followed by more identifier chars
            if self.is_at_end or not (self.string[self.pos].isalnum() or self.string[self.pos] == '_'):
                self.pos = backtrack
                break
        return path if path else None

    def scan_keyword(self, keyword: str) -> Optional[str]:
        backtrack = self.pos
        ident = self.scan_identifier()
        if ident == keyword:
            return keyword
        self.pos = backtrack
        return None


# =============================================================================
# Token & Tag Types
# =============================================================================

class TokenType(Enum):
    TEXT = auto()
    TAG = auto()
    NEWLINE = auto()
    WHITESPACE = auto()


class ComparisonOp(Enum):
    EQUALS = auto()
    NOT_EQUALS = auto()


class ConditionalTokenType(Enum):
    NOT = auto()
    AND = auto()
    OR = auto()
    START_PAREN = auto()
    END_PAREN = auto()
    TERMINAL = auto()
    STRING = auto()
    COMPARISON_OP = auto()


@dataclass
class ConditionalToken:
    type: ConditionalTokenType
    value: Any = None


# =============================================================================
# Tag Types
# =============================================================================

class TagType(Enum):
    IF = auto()
    FOR = auto()
    ELSE = auto()
    END = auto()
    IMPORT = auto()
    VARIABLE = auto()


@dataclass
class Tag:
    type: TagType
    condition: Any = None          # ConditionalExpression for IF
    variable: str = ""             # loop variable for FOR
    sequence: list = field(default_factory=list)  # path for FOR
    file: str = ""                 # filepath for IMPORT
    path: list = field(default_factory=list)      # path for VARIABLE
    transformers: list = field(default_factory=list)  # for VARIABLE


@dataclass
class Token:
    type: TokenType
    text: str = ""
    tag: Optional[Tag] = None


# =============================================================================
# Conditional Expression
# =============================================================================

class ExprType(Enum):
    OR = auto()
    AND = auto()
    NOT = auto()
    TERMINAL = auto()
    TERMINAL_COMPARE = auto()


@dataclass
class ConditionalExpression:
    type: ExprType
    children: list = field(default_factory=list)
    path: list = field(default_factory=list)
    string: str = ""
    op: Optional[ComparisonOp] = None

    def evaluate(self, context: dict) -> bool:
        if self.type == ExprType.OR:
            for child in self.children:
                if child.evaluate(context):
                    return True
            return False

        elif self.type == ExprType.AND:
            for child in self.children:
                if not child.evaluate(context):
                    return False
            return True

        elif self.type == ExprType.NOT:
            return not self.children[0].evaluate(context)

        elif self.type == ExprType.TERMINAL:
            value = context_value(self.path, context)
            if value is None:
                return False
            if isinstance(value, bool):
                return value
            return True

        elif self.type == ExprType.TERMINAL_COMPARE:
            value = context_value(self.path, context)
            if value is not None:
                str_value = str(value)
                if self.op == ComparisonOp.EQUALS:
                    return str_value == self.string
                else:
                    return str_value != self.string
            else:
                # Value is None
                if self.op == ComparisonOp.EQUALS:
                    return self.string == ""
                else:  # NOT_EQUALS
                    return self.string != ""

        return False


# =============================================================================
# Context Value Resolution
# =============================================================================

def context_value(path: list, node: Any) -> Any:
    if node is None:
        return None
    if not path:
        return node
    if isinstance(node, dict):
        key = path[0]
        if key not in node:
            return None
        return context_value(path[1:], node[key])
    # For non-dict nodes with remaining path, return None
    return None


# =============================================================================
# Condition Lexer
# =============================================================================

class ConditionLexer:

    def tokenize(self, string: str) -> list:
        scanner = Scanner(string)
        return self.tokenize_scanner(scanner)

    def tokenize_scanner(self, scanner: Scanner) -> list:
        tokens = []
        scanner.scan_whitespace()

        while not scanner.is_at_end:
            if scanner.scan_keyword("or") is not None:
                tokens.append(ConditionalToken(ConditionalTokenType.OR))
            elif scanner.scan_keyword("and") is not None:
                tokens.append(ConditionalToken(ConditionalTokenType.AND))
            elif scanner.scan_keyword("not") is not None:
                tokens.append(ConditionalToken(ConditionalTokenType.NOT))
            elif scanner.scan_string("(") is not None:
                tokens.append(ConditionalToken(ConditionalTokenType.START_PAREN))
            elif scanner.scan_string(")") is not None:
                tokens.append(ConditionalToken(ConditionalTokenType.END_PAREN))
            elif scanner.scan_string("==") is not None:
                tokens.append(ConditionalToken(ConditionalTokenType.COMPARISON_OP, ComparisonOp.EQUALS))
            elif scanner.scan_string("!=") is not None:
                tokens.append(ConditionalToken(ConditionalTokenType.COMPARISON_OP, ComparisonOp.NOT_EQUALS))
            elif scanner.scan_string('"') is not None:
                s = scanner.scan_up_to_string('"')
                if s is None:
                    s = ""
                if scanner.scan_string('"') is None:
                    raise ValueError("Unterminated string in condition")
                tokens.append(ConditionalToken(ConditionalTokenType.STRING, s))
            elif scanner.scan_string("'") is not None:
                s = scanner.scan_up_to_string("'")
                if s is None:
                    s = ""
                if scanner.scan_string("'") is None:
                    raise ValueError("Unterminated string in condition")
                tokens.append(ConditionalToken(ConditionalTokenType.STRING, s))
            else:
                path = scanner.scan_path()
                if path is not None:
                    tokens.append(ConditionalToken(ConditionalTokenType.TERMINAL, path))
                else:
                    raise ValueError(f"Invalid condition at position {scanner.pos}")
            scanner.scan_whitespace()

        return tokens


# =============================================================================
# Condition Parser
# =============================================================================

class ConditionParser:
    """Recursive descent parser for condition expressions.

    Grammar:
        expr      := term ('or' term)*
        term      := factor ('and' factor)*
        factor    := 'not'? ( statement | '(' expr ')' )
        statement := terminal ( ('==' | '!=') string )?
    """

    def parse(self, tokens: list) -> ConditionalExpression:
        result = self._parse_expr(tokens, 0)
        if result is None:
            raise ValueError("Failed to parse condition")
        condition, index = result
        if index < len(tokens):
            raise ValueError("Unexpected tokens after condition")
        return condition

    def _parse_expr(self, tokens, i):
        terms = []
        result = self._parse_term(tokens, i)
        if result is None:
            return None
        condition, i = result
        terms.append(condition)

        while i < len(tokens) and tokens[i].type == ConditionalTokenType.OR:
            i += 1
            result = self._parse_term(tokens, i)
            if result is None:
                raise ValueError("Expected term after 'or'")
            condition, i = result
            terms.append(condition)

        return ConditionalExpression(ExprType.OR, children=terms), i

    def _parse_term(self, tokens, i):
        factors = []
        result = self._parse_factor(tokens, i)
        if result is None:
            return None
        condition, i = result
        factors.append(condition)

        while i < len(tokens) and tokens[i].type == ConditionalTokenType.AND:
            i += 1
            result = self._parse_factor(tokens, i)
            if result is None:
                raise ValueError("Expected factor after 'and'")
            condition, i = result
            factors.append(condition)

        return ConditionalExpression(ExprType.AND, children=factors), i

    def _parse_factor(self, tokens, i):
        if i >= len(tokens):
            return None

        should_invert = False
        if tokens[i].type == ConditionalTokenType.NOT:
            should_invert = True
            i += 1

        if i >= len(tokens):
            raise ValueError("Unexpected end of condition")

        if tokens[i].type == ConditionalTokenType.START_PAREN:
            i += 1
            result = self._parse_expr(tokens, i)
            if result is None:
                raise ValueError("Expected expression after '('")
            condition, i = result
            if i >= len(tokens) or tokens[i].type != ConditionalTokenType.END_PAREN:
                raise ValueError("Expected ')'")
            i += 1
            if should_invert:
                return ConditionalExpression(ExprType.NOT, children=[condition]), i
            return condition, i

        elif tokens[i].type == ConditionalTokenType.TERMINAL:
            result = self._parse_statement(tokens, i)
            if result is None:
                raise ValueError("Expected statement")
            condition, i = result
            if should_invert:
                return ConditionalExpression(ExprType.NOT, children=[condition]), i
            return condition, i

        else:
            raise ValueError(f"Unexpected token: {tokens[i]}")

    def _parse_statement(self, tokens, i):
        if i >= len(tokens) or tokens[i].type != ConditionalTokenType.TERMINAL:
            return None
        path = tokens[i].value
        i += 1

        if i >= len(tokens):
            return ConditionalExpression(ExprType.TERMINAL, path=path), i

        if tokens[i].type == ConditionalTokenType.COMPARISON_OP:
            op = tokens[i].value
            i += 1
            if i >= len(tokens) or tokens[i].type != ConditionalTokenType.STRING:
                raise ValueError("Expected string after comparison operator")
            string = tokens[i].value
            i += 1
            return ConditionalExpression(ExprType.TERMINAL_COMPARE, path=path, string=string, op=op), i

        return ConditionalExpression(ExprType.TERMINAL, path=path), i


# =============================================================================
# Tag Parser
# =============================================================================

class TagParser:

    def parse(self, string: str) -> Tag:
        scanner = Scanner(string)
        scanner.scan_whitespace()

        tag = self._scan_if(scanner)
        if tag:
            return tag
        tag = self._scan_for(scanner)
        if tag:
            return tag
        tag = self._scan_else(scanner)
        if tag:
            return tag
        tag = self._scan_end(scanner)
        if tag:
            return tag
        tag = self._scan_import(scanner)
        if tag:
            return tag
        tag = self._scan_variable(scanner)
        if tag:
            return tag
        raise ValueError(f"Invalid tag: {string}")

    def _scan_if(self, scanner: Scanner) -> Optional[Tag]:
        backtrack = scanner.pos
        if scanner.scan_string("if") is None:
            return None
        if scanner.scan_whitespace() is None:
            if scanner.is_at_end:
                raise ValueError("Invalid if tag")
            scanner.pos = backtrack
            return None

        cond_lexer = ConditionLexer()
        cond_tokens = cond_lexer.tokenize_scanner(scanner)
        condition = ConditionParser().parse(cond_tokens)
        return Tag(TagType.IF, condition=condition)

    def _scan_for(self, scanner: Scanner) -> Optional[Tag]:
        backtrack = scanner.pos
        if scanner.scan_string("for") is None:
            return None
        if scanner.scan_whitespace() is None:
            if scanner.is_at_end:
                raise ValueError("Invalid for tag")
            scanner.pos = backtrack
            return None
        variable = scanner.scan_identifier()
        if variable is None:
            raise ValueError("Expected variable name in for tag")
        if scanner.scan_whitespace() is None:
            scanner.pos = backtrack
            return None
        if scanner.scan_string("in") is None:
            raise ValueError("Expected 'in' in for tag")
        if scanner.scan_whitespace() is None:
            raise ValueError("Expected whitespace after 'in'")
        sequence = scanner.scan_path()
        if sequence is None:
            raise ValueError("Expected path in for tag")
        scanner.scan_whitespace()
        if not scanner.is_at_end:
            raise ValueError("Unexpected content after for tag")
        return Tag(TagType.FOR, variable=variable, sequence=sequence)

    def _scan_else(self, scanner: Scanner) -> Optional[Tag]:
        backtrack = scanner.pos
        if scanner.scan_string("else") is None:
            return None
        scanner.scan_whitespace()
        if not scanner.is_at_end:
            scanner.pos = backtrack
            return None
        return Tag(TagType.ELSE)

    def _scan_end(self, scanner: Scanner) -> Optional[Tag]:
        backtrack = scanner.pos
        if scanner.scan_string("end") is None:
            return None
        scanner.scan_whitespace()
        if not scanner.is_at_end:
            scanner.pos = backtrack
            return None
        return Tag(TagType.END)

    def _scan_import(self, scanner: Scanner) -> Optional[Tag]:
        backtrack = scanner.pos
        if scanner.scan_string("import") is None:
            return None
        if scanner.scan_whitespace() is None:
            if scanner.is_at_end:
                raise ValueError("Invalid import tag")
            scanner.pos = backtrack
            return None
        if scanner.scan_string('"') is None:
            if scanner.is_at_end:
                raise ValueError("Invalid import tag")
            scanner.pos = backtrack
            return None
        file_path = scanner.scan_up_to_characters_from(set('"\n'))
        if file_path is None:
            if scanner.is_at_end:
                raise ValueError("Invalid import tag")
            scanner.pos = backtrack
            return None
        if scanner.scan_string('"') is None:
            if scanner.is_at_end:
                raise ValueError("Invalid import tag")
            scanner.pos = backtrack
            return None
        return Tag(TagType.IMPORT, file=file_path)

    def _scan_variable(self, scanner: Scanner) -> Optional[Tag]:
        backtrack = scanner.pos
        transformers = self._scan_transformers(scanner)
        path = scanner.scan_path()
        if path is None:
            scanner.pos = backtrack
            return None
        scanner.scan_whitespace()
        if not scanner.is_at_end:
            raise ValueError("Invalid variable tag")
        return Tag(TagType.VARIABLE, path=path, transformers=transformers)

    def _scan_transformers(self, scanner: Scanner) -> list:
        transformers = []
        while scanner.scan_string("#") is not None:
            name = scanner.scan_identifier()
            if name is None:
                raise ValueError("Expected transformer name after #")
            transformers.append(name)
            scanner.scan_whitespace()
        return transformers


# =============================================================================
# Main Lexer
# =============================================================================

class Lexer:

    def __init__(self, tag_start: str = "<{", tag_end: str = "}>"):
        self.tag_start = tag_start
        self.tag_end = tag_end

    def tokenize(self, string: str) -> list:
        tokens = []
        scanner = Scanner(string)

        while True:
            tag_token = self._scan_tag(scanner)
            if tag_token is not None:
                tokens.append(tag_token)
            elif scanner.scan_string("\n") is not None:
                tokens.append(Token(TokenType.NEWLINE))
            else:
                text_token = self._scan_text(scanner)
                if text_token is not None:
                    tokens.append(text_token)
                else:
                    break

        return tokens

    def _scan_tag(self, scanner: Scanner) -> Optional[Token]:
        if scanner.scan_string(self.tag_start) is None:
            return None
        tag_string = scanner.scan_up_to_string(self.tag_end)
        if tag_string is None:
            raise ValueError("Missing tag end")
        if scanner.scan_string(self.tag_end) is None:
            raise ValueError("Missing tag end")
        tag = TagParser().parse(tag_string)
        return Token(TokenType.TAG, tag=tag)

    def _scan_text(self, scanner: Scanner) -> Optional[Token]:
        first_tag_char = self.tag_start[0] if self.tag_start else None
        if first_tag_char is None:
            return None

        stop_chars = set("\n" + first_tag_char)
        scanned_text = scanner.scan_up_to_characters_from(stop_chars)

        saved_pos = scanner.pos

        if scanned_text is None:
            if scanner.is_at_end:
                return None
            elif not scanner.is_at_end and scanner.current_char == '\n':
                return Token(TokenType.WHITESPACE, text="")
            elif scanner.scan_string(self.tag_start) is not None:
                scanner.pos = saved_pos
                return Token(TokenType.WHITESPACE, text="")
            else:
                scanned_text = ""

        text = scanned_text

        if scanner.is_at_end:
            if self._is_whitespace_only(text):
                return Token(TokenType.WHITESPACE, text=text)
            else:
                return Token(TokenType.TEXT, text=text)

        saved_pos = scanner.pos
        if scanner.scan_string("\n") is not None:
            scanner.pos = saved_pos
            if self._is_whitespace_only(text):
                return Token(TokenType.WHITESPACE, text=text)
            else:
                return Token(TokenType.TEXT, text=text)

        if scanner.scan_string(self.tag_start) is not None:
            scanner.pos = saved_pos
            if self._is_whitespace_only(text):
                return Token(TokenType.WHITESPACE, text=text)
            else:
                return Token(TokenType.TEXT, text=text)

        # We hit the first character of tag_start but it's not actually a tag
        ch = scanner.scan_character()
        return Token(TokenType.TEXT, text=text + (ch or ""))

    def _is_whitespace_only(self, s: str) -> bool:
        return s.strip(" ") == ""


# =============================================================================
# AST Nodes
# =============================================================================

class Node:
    pass


@dataclass
class TextNode(Node):
    text: str


@dataclass
class VariableNode(Node):
    path: list
    transformers: list


@dataclass
class IfNode(Node):
    condition: ConditionalExpression
    children: list


@dataclass
class ElseNode(Node):
    children: list


@dataclass
class ForNode(Node):
    variable: str
    sequence: list
    children: list


@dataclass
class ImportNode(Node):
    file: str


# =============================================================================
# Parser (Tokens -> AST)
# =============================================================================

class Parser:

    def parse(self, tokens: list) -> list:
        filtered = self._remove_unwanted_newlines(tokens)
        result = self._parse(filtered, 0, 0)
        return result[0]

    def _parse(self, tokens, index, level):
        nodes = []
        i = index

        while i < len(tokens):
            token = tokens[i]

            if token.type == TokenType.TEXT:
                nodes.append(TextNode(token.text))
                i += 1

            elif token.type == TokenType.NEWLINE:
                nodes.append(TextNode("\n"))
                i += 1

            elif token.type == TokenType.WHITESPACE:
                nodes.append(TextNode(token.text))
                i += 1

            elif token.type == TokenType.TAG:
                tag = token.tag

                if tag.type == TagType.VARIABLE:
                    nodes.append(VariableNode(tag.path, tag.transformers))
                    i += 1

                elif tag.type == TagType.IF:
                    i += 1
                    child_nodes, i = self._parse(tokens, i, level + 1)
                    nodes.append(IfNode(tag.condition, child_nodes))

                elif tag.type == TagType.FOR:
                    i += 1
                    child_nodes, i = self._parse(tokens, i, level + 1)
                    nodes.append(ForNode(tag.variable, tag.sequence, child_nodes))

                elif tag.type == TagType.ELSE:
                    if level == 0:
                        raise ValueError("Unbalanced else")
                    i += 1
                    child_nodes, i = self._parse(tokens, i, level + 1)
                    nodes.append(ElseNode(child_nodes))
                    return nodes, i

                elif tag.type == TagType.END:
                    if level == 0:
                        raise ValueError("Unbalanced end")
                    i += 1
                    return nodes, i

                elif tag.type == TagType.IMPORT:
                    nodes.append(ImportNode(tag.file))
                    i += 1

        if level > 0:
            raise ValueError(f"Unbalanced if or for at index {i}")

        return nodes, i

    def _is_tag_newline_sensitive(self, tag: Tag) -> bool:
        return tag.type in (TagType.IF, TagType.FOR, TagType.ELSE, TagType.END, TagType.IMPORT)

    def _remove_unwanted_newlines(self, tokens: list) -> list:
        filtered = []
        minus4 = None
        minus3 = None
        minus2 = None
        minus1 = None

        for token in tokens:
            if token.type == TokenType.NEWLINE:
                skip = False

                # Pattern 1: [start] TAG NEWLINE (minus2 is None means start)
                if (minus1 is not None and minus1.type == TokenType.TAG
                        and self._is_tag_newline_sensitive(minus1.tag)
                        and minus2 is None):
                    skip = True

                # Pattern 2: NEWLINE TAG NEWLINE
                elif (minus2 is not None and minus2.type == TokenType.NEWLINE
                      and minus1 is not None and minus1.type == TokenType.TAG
                      and self._is_tag_newline_sensitive(minus1.tag)):
                    skip = True

                # Pattern 3: NEWLINE TAG WHITESPACE NEWLINE
                elif (minus3 is not None and minus3.type == TokenType.NEWLINE
                      and minus2 is not None and minus2.type == TokenType.TAG
                      and self._is_tag_newline_sensitive(minus2.tag)
                      and minus1 is not None and minus1.type == TokenType.WHITESPACE):
                    skip = True

                # Pattern 4: NEWLINE WHITESPACE TAG NEWLINE
                elif (minus3 is not None and minus3.type == TokenType.NEWLINE
                      and minus2 is not None and minus2.type == TokenType.WHITESPACE
                      and minus1 is not None and minus1.type == TokenType.TAG
                      and self._is_tag_newline_sensitive(minus1.tag)):
                    skip = True

                # Pattern 5: NEWLINE WHITESPACE TAG WHITESPACE NEWLINE
                elif (minus4 is not None and minus4.type == TokenType.NEWLINE
                      and minus3 is not None and minus3.type == TokenType.WHITESPACE
                      and minus2 is not None and minus2.type == TokenType.TAG
                      and self._is_tag_newline_sensitive(minus2.tag)
                      and minus1 is not None and minus1.type == TokenType.WHITESPACE):
                    skip = True

                if not skip:
                    filtered.append(token)
            else:
                filtered.append(token)

            minus4 = minus3
            minus3 = minus2
            minus2 = minus1
            minus1 = token

        return filtered


# =============================================================================
# Transformers
# =============================================================================

TRANSFORMERS = {
    "lowercased": lambda v: v.lower() if isinstance(v, str) else v,
    "uppercased": lambda v: v.upper() if isinstance(v, str) else v,
    "uppercasingFirstLetter": lambda v: (v[0].upper() + v[1:] if v else v) if isinstance(v, str) else v,
    "lowercasingFirstLetter": lambda v: (v[0].lower() + v[1:] if v else v) if isinstance(v, str) else v,
    "trimmed": lambda v: v.strip() if isinstance(v, str) else v,
    "removingWhitespace": lambda v: ''.join(v.split()) if isinstance(v, str) else v,
    # Note: Swift code maps collapsingWhitespace to removingWhitespace (bug).
    # We replicate the Swift behavior for compatibility.
    "collapsingWhitespace": lambda v: ''.join(v.split()) if isinstance(v, str) else v,
}


# =============================================================================
# Renderer
# =============================================================================

class Renderer:

    def __init__(self, tag_start: str = "<{", tag_end: str = "}>", root: Optional[str] = None):
        self.tag_start = tag_start
        self.tag_end = tag_end
        self.root = root

    def render(self, nodes: list, context: dict) -> str:
        parts = self._render_parts(nodes, context)
        return "".join(parts)

    def _render_parts(self, nodes: list, user_context: dict) -> list:
        # Build context with transformers + user context
        context = {}
        context.update(TRANSFORMERS)
        context.update(user_context)

        parts = []
        for node in nodes:
            if isinstance(node, TextNode):
                parts.append(node.text)

            elif isinstance(node, VariableNode):
                value = context_value(node.path, context)
                for t_name in node.transformers:
                    t_func = context.get(t_name)
                    if callable(t_func):
                        value = t_func(value)
                if value is not None:
                    parts.append(str(value))

            elif isinstance(node, IfNode):
                if node.condition.evaluate(context):
                    parts.extend(self._render_parts(node.children, context))
                else:
                    for child in node.children:
                        if isinstance(child, ElseNode):
                            parts.extend(self._render_parts(child.children, context))
                            break

            elif isinstance(node, ForNode):
                seq = context_value(node.sequence, context)
                if isinstance(seq, list):
                    for item in seq:
                        new_context = dict(context)
                        new_context[node.variable] = item
                        parts.extend(self._render_parts(node.children, new_context))

            elif isinstance(node, ImportNode):
                if self.root:
                    file_path = os.path.join(self.root, node.file)
                else:
                    file_path = node.file
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                template = Template(content, self.tag_start, self.tag_end)
                parts.append(template.render(context, root=self.root))

        return parts


# =============================================================================
# Template Facade
# =============================================================================

class Template:

    def __init__(self, text: str, tag_start: str = "<{", tag_end: str = "}>"):
        self.text = text
        self.tag_start = tag_start
        self.tag_end = tag_end

    def render(self, context: dict, root: Optional[str] = None) -> str:
        lexer = Lexer(self.tag_start, self.tag_end)
        tokens = lexer.tokenize(self.text)
        parser = Parser()
        nodes = parser.parse(tokens)
        renderer = Renderer(self.tag_start, self.tag_end, root)
        return renderer.render(nodes, context)


# =============================================================================
# Bootstrapp Instantiator
# =============================================================================

class BootstrappInstantiator:

    def __init__(self, template_dir: str, params: dict, exclude_packages: list,
                 output_dir: Optional[str] = None, verbose: bool = False):
        self.template_dir = os.path.abspath(template_dir)
        self.params = params
        self.exclude_packages = exclude_packages
        self.output_dir_override = output_dir
        self.verbose = verbose
        self.spec = None
        self.blacklisted_dirs = []
        self.blacklisted_files = []

    def log(self, msg: str):
        if self.verbose:
            print(msg, file=sys.stderr)

    def run(self) -> str:
        self.log(f"Loading spec from {self.template_dir}")
        self.spec = self._load_spec()

        context = self._build_context()
        output_path = self._prepare_output_dir(context)
        content_path = os.path.join(self.template_dir, "Content")

        self.log(f"Content path: {content_path}")
        self.log(f"Output path: {output_path}")

        # Build blacklists
        self._build_directory_blacklist(context)
        self._build_file_blacklist(context)

        # Collect all subpaths under Content/
        all_subpaths = []
        for dirpath, dirnames, filenames in os.walk(content_path):
            rel = os.path.relpath(dirpath, content_path)
            if rel != ".":
                all_subpaths.append(("dir", rel))
            for f in filenames:
                file_rel = os.path.join(rel, f) if rel != "." else f
                all_subpaths.append(("file", file_rel))

        # Instantiate directories first
        dirs = [(t, p) for t, p in all_subpaths if t == "dir"]
        for _, subpath in sorted(dirs, key=lambda x: x[1]):
            if not self._should_include_directory(subpath):
                self.log(f"  Skipping dir (blacklisted): {subpath}")
                continue
            rendered_path = Template(subpath).render(context)
            dest = os.path.join(output_path, rendered_path)
            os.makedirs(dest, exist_ok=True)
            self.log(f"  Created dir: {rendered_path}")

        # Instantiate files
        files = [(t, p) for t, p in all_subpaths if t == "file"]
        for _, subpath in files:
            if not self._should_include_directory(subpath):
                self.log(f"  Skipping file (dir blacklisted): {subpath}")
                continue
            if not self._should_include_file(subpath):
                self.log(f"  Skipping file (file blacklisted): {subpath}")
                continue

            rendered_path = Template(subpath).render(context)
            source = os.path.join(content_path, subpath)
            dest = os.path.join(output_path, rendered_path)

            # Ensure parent directory exists
            os.makedirs(os.path.dirname(dest), exist_ok=True)

            if self._should_parametrize_file(rendered_path):
                try:
                    with open(source, 'r', encoding='utf-8') as f:
                        content = f.read()
                    rendered_content = Template(content).render(context, root=content_path)
                    with open(dest, 'w', encoding='utf-8') as f:
                        f.write(rendered_content)
                    self.log(f"  Rendered: {rendered_path}")
                except UnicodeDecodeError:
                    # Fallback: binary copy if file can't be read as UTF-8
                    shutil.copy2(source, dest)
                    self.log(f"  Copied (binary fallback): {rendered_path}")
            else:
                shutil.copy2(source, dest)
                self.log(f"  Copied: {rendered_path}")

        # XcodeGen (if Xcode Project type)
        project_type = self.spec.get("type", "")
        if project_type == "Xcode Project":
            project_spec_file = self.spec.get("projectSpecification", "")
            if project_spec_file:
                xcodeproj_path = self._run_xcodegen(output_path, project_spec_file, context)
                if xcodeproj_path:
                    return xcodeproj_path

        return output_path

    def _load_spec(self) -> dict:
        spec_path = os.path.join(self.template_dir, "Bootstrapp.json")
        with open(spec_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _build_context(self) -> dict:
        context = {}

        # Date variables
        now = datetime.datetime.now()
        context["CURRENT_YEAR"] = now.strftime("%Y")
        context["CURRENT_DATE"] = now.strftime("%Y-%m-%d")
        context["CURRENT_DATETIME"] = now.isoformat()
        context["CURRENT_TIME"] = now.strftime("%H:%M:%S")

        # Template version
        context["TEMPLATE_VERSION"] = self.spec.get("templateVersion", "1.0.0")

        # Substitutions
        for k, v in self.spec.get("substitutions", {}).items():
            context[k] = v

        # Parameters
        for param in self.spec.get("parameters", []):
            param_id = param["id"]
            param_type = param.get("type", "String")

            if param_id in self.params:
                # User-provided value
                value = self.params[param_id]
                if param_type == "Bool":
                    if isinstance(value, str):
                        value = value.lower() == "true"
                elif param_type == "Option":
                    # Value is already the option string
                    pass
                context[param_id] = value
            else:
                # Use default
                if param_type == "String":
                    default = param.get("default", "")
                    context[param_id] = default if default else None
                elif param_type == "Bool":
                    context[param_id] = param.get("default", False)
                elif param_type == "Option":
                    options = param.get("options", [])
                    default_idx = param.get("default", 0)
                    if options and 0 <= default_idx < len(options):
                        context[param_id] = options[default_idx]
                    else:
                        context[param_id] = None

        # Packages
        packages = list(self.spec.get("packages", []))
        packages = [p for p in packages if p.get("name") not in self.exclude_packages]
        context["packages"] = packages

        return context

    def _prepare_output_dir(self, context: dict) -> str:
        if self.output_dir_override:
            output_path = self.output_dir_override
        else:
            output_dir_name_template = self.spec.get("outputDirectoryName", "Output")
            rendered_name = Template(output_dir_name_template).render(context)
            date_str = datetime.date.today().strftime("%Y-%m-%d")
            output_path = os.path.join("/tmp", "Results", date_str, rendered_name)

        if os.path.exists(output_path):
            shutil.rmtree(output_path)
        os.makedirs(output_path, exist_ok=True)

        return output_path

    def _build_directory_blacklist(self, context: dict):
        self.blacklisted_dirs = []
        for entry in self.spec.get("includeDirectories", []):
            condition_str = entry.get("if", "")
            cond_tokens = ConditionLexer().tokenize(condition_str)
            condition = ConditionParser().parse(cond_tokens)
            if condition.evaluate(context):
                continue  # Condition is true, include these dirs
            for d in entry.get("directories", []):
                self.blacklisted_dirs.append(d)
        self.log(f"  Blacklisted dirs: {self.blacklisted_dirs}")

    def _build_file_blacklist(self, context: dict):
        self.blacklisted_files = []
        for entry in self.spec.get("includeFiles", []):
            condition_str = entry.get("if", "")
            cond_tokens = ConditionLexer().tokenize(condition_str)
            condition = ConditionParser().parse(cond_tokens)
            if condition.evaluate(context):
                continue  # Condition is true, include these files
            for f in entry.get("files", []):
                self.blacklisted_files.append(f)
        self.log(f"  Blacklisted files: {self.blacklisted_files}")

    def _should_include_directory(self, path: str) -> bool:
        for bl_dir in self.blacklisted_dirs:
            if path == bl_dir or path.startswith(bl_dir + "/"):
                return False
        return True

    def _should_include_file(self, path: str) -> bool:
        filename = os.path.basename(path)
        if filename == ".ignored-placeholder":
            return False
        for bl_file in self.blacklisted_files:
            if path == bl_file:
                return False
        return True

    def _should_parametrize_file(self, rendered_path: str) -> bool:
        filename = os.path.basename(rendered_path)
        patterns = self.spec.get("parametrizableFiles", [])
        for pattern in patterns:
            anchored = f"^{pattern}$"
            if re.match(anchored, filename):
                return True
        return False

    def _run_xcodegen(self, output_path: str, spec_file: str, context: dict) -> Optional[str]:
        spec_path = os.path.join(output_path, spec_file)
        if not os.path.exists(spec_path):
            self.log(f"  XcodeGen spec not found: {spec_path}")
            return None

        # Check for xcodegen
        xcodegen = shutil.which("xcodegen")
        if xcodegen is None:
            print("WARNING: xcodegen not found in PATH. Skipping Xcode project generation.", file=sys.stderr)
            print("  Install it with: brew install xcodegen", file=sys.stderr)
            print("  The rendered template files are still available in the output directory.", file=sys.stderr)
            return None

        self.log(f"  Running xcodegen with spec: {spec_path}")

        # Check for presets directory
        presets_path = os.path.join(self.template_dir, "Presets")
        cwd = presets_path if os.path.isdir(presets_path) else output_path

        try:
            result = subprocess.run(
                [xcodegen, "generate", "--spec", spec_path, "--project", output_path],
                cwd=cwd,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                self.log(f"  xcodegen stderr: {result.stderr}")
                self.log(f"  xcodegen stdout: {result.stdout}")
            else:
                self.log(f"  xcodegen completed successfully")
        except Exception as e:
            self.log(f"  xcodegen error: {e}")
            return None

        # Find the generated .xcodeproj
        for item in os.listdir(output_path):
            if item.endswith(".xcodeproj"):
                xcodeproj_path = os.path.join(output_path, item)
                self._write_header_template(xcodeproj_path, context)
                return xcodeproj_path

        return None

    def _write_header_template(self, xcodeproj_path: str, context: dict):
        year = context.get("CURRENT_YEAR", "YEAR")
        holder = context.get("COPYRIGHT_HOLDER", "COPYRIGHT_HOLDER")
        shared_data = os.path.join(xcodeproj_path, "xcshareddata")
        os.makedirs(shared_data, exist_ok=True)
        plist_path = os.path.join(shared_data, "IDETemplateMacros.plist")
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>FILEHEADER</key>
    <string>
//  Copyright \u00a9 {year} {holder}. All rights reserved.
//</string>
</dict>
</plist>
"""
        with open(plist_path, 'w', encoding='utf-8') as f:
            f.write(plist_content)
        self.log(f"  Wrote IDETemplateMacros.plist")


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Instantiate a project from a Bootstrapp template bundle."
    )
    parser.add_argument("template_dir", help="Path to the template bundle directory")
    parser.add_argument("--param", action="append", default=[],
                        help="Parameter in KEY=VALUE format (repeatable)")
    parser.add_argument("--exclude-package", action="append", default=[], dest="exclude_packages",
                        help="Exclude a spec-defined package by name (repeatable)")
    parser.add_argument("--output-dir", default=None,
                        help="Override the output directory")
    parser.add_argument("--verbose", action="store_true",
                        help="Print progress information to stderr")
    args = parser.parse_args()

    # Parse params
    params = {}
    for p in args.param:
        idx = p.find("=")
        if idx == -1:
            print(f"Error: Invalid parameter format '{p}'. Expected KEY=VALUE.", file=sys.stderr)
            sys.exit(1)
        key = p[:idx]
        value = p[idx + 1:]
        # Parse bool strings
        if value.lower() == "true":
            params[key] = True
        elif value.lower() == "false":
            params[key] = False
        else:
            params[key] = value

    instantiator = BootstrappInstantiator(
        template_dir=args.template_dir,
        params=params,
        exclude_packages=args.exclude_packages,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )

    try:
        output_path = instantiator.run()
        print(output_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
