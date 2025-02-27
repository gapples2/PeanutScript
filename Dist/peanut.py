#!/bin/python3
# region Imports + Constants
import math
import re
import string
import os
import time
import base64
from math import floor

DIGITS = '0123456789'
LETTERS = string.ascii_letters
LETTERS_DIGITS = LETTERS + DIGITS

FILE_NAME = 'CONSOLE'


def string_with_arrows(text, pos_start, pos_end):
    result = ''

    # Calculate indices
    idx_start = max(text.rfind('\n', 0, pos_start.idx), 0)
    idx_end = text.find('\n', idx_start + 1)
    if idx_end < 0: idx_end = len(text)

    # Generate each line
    line_count = pos_end.ln - pos_start.ln + 1
    for i in range(line_count):
        # Calculate line columns
        line = text[idx_start:idx_end]
        col_start = pos_start.col if i == 0 else 0
        col_end = pos_end.col if i == line_count - 1 else len(line) - 1

        # Append to result
        result += line + '\n'
        result += ' ' * col_start + '^' * (col_end - col_start)

        # Re-calculate indices
        idx_start = idx_end
        idx_end = text.find('\n', idx_start + 1)
        if idx_end < 0: idx_end = len(text)

    return result.replace('\t', '')


def containsAny(text, chars):
    return 1 in [c in text for c in chars]


# endregion


# region Errors, Warning, Error Types, and Warning Types
class Error:
    def __init__(self, pos_start, pos_end, error_name, details):
        self.pos_start = pos_start
        self.pos_end = pos_end
        self.error_name = error_name
        self.details = details

    def as_string(self):
        result = f'{self.error_name}: {self.details}'
        result += f'\nTrace: File {self.pos_start.fn}, line {self.pos_start.ln + 1}'
        result += '\n\n' + string_with_arrows(self.pos_start.ftxt, self.pos_start, self.pos_end)
        return result


class Warning:
    def __init__(self, pos_start, pos_end, warning_name, details):
        self.pos_start = pos_start
        self.pos_end = pos_end
        self.warning_name = warning_name
        self.details = details

    def as_string(self):
        result = f'{self.warning_name}: {self.details}'
        return result


class IllegalCharError(Error):
    def __init__(self, pos_start, pos_end, details):
        super().__init__(pos_start, pos_end, 'Illegal Character', details)


class ExpectedCharError(Error):
    def __init__(self, pos_start, pos_end, details):
        super().__init__(pos_start, pos_end, 'Expected Character', details)


class InvalidSyntaxError(Error):
    def __init__(self, pos_start, pos_end, details):
        super().__init__(pos_start, pos_end, 'Invalid Syntax', details)


class RTError(Error):
    def __init__(self, pos_start, pos_end, details, context):
        super().__init__(pos_start, pos_end, 'Runtime Error', details)
        self.context = context

    def as_string(self):
        result = self.generate_traceback()
        result += f'{self.error_name}: {self.details}'
        result += '\n\n' + string_with_arrows(self.pos_start.ftxt, self.pos_start, self.pos_end)
        return result

    def generate_traceback(self):
        result = ''
        pos = self.pos_start
        ctx = self.context

        while ctx:
            result = f'  File {pos.fn}, line {str(pos.ln + 1)}, in {ctx.display_name}\n' + result
            pos = ctx.parent_entry_pos
            ctx = ctx.parent

        return 'Trace:\n' + result


class RTWarning(Warning):
    def __init__(self, pos_start, pos_end, details, context):
        super().__init__(pos_start, pos_end, 'Runtime Error', details)
        self.context = context

    def as_string(self):
        result = self.generate_traceback()
        return result

    def generate_traceback(self):
        result = ''
        pos = self.pos_start
        ctx = self.context

        while ctx:
            result = f'  File {pos.fn}, line {str(pos.ln + 1)}, in {ctx.display_name}\n' + result
            pos = ctx.parent_entry_pos
            ctx = ctx.parent

        return 'Trace:\n' + result


# endregion


class Position:
    def __init__(self, idx, ln, col, fn, ftxt):
        self.idx = idx
        self.ln = ln
        self.col = col
        self.fn = fn
        self.ftxt = ftxt

    def advance(self, current_char=None):
        self.idx += 1
        self.col += 1

        if current_char == '\n':
            self.ln += 1
            self.col = 0

        return self

    def copy(self):
        return Position(self.idx, self.ln, self.col, self.fn, self.ftxt)


# region Tokens and Keywords
TT_INT = 'INT'
TT_FLOAT = 'FLOAT'
TT_STRING = 'STRING'
TT_IDENTIFIER = 'IDENTIFIER'
TT_KEYWORD = 'KEYWORD'
TT_PLUS = 'PLUS'
TT_MINUS = 'MINUS'
TT_MUL = 'MUL'
TT_DIV = 'DIV'
TT_POW = 'POW'
TT_MOD = 'MOD'
TT_EQ = 'EQ'
TT_LPAREN = 'LPAREN'
TT_RPAREN = 'RPAREN'
TT_LSQUARE = 'LSQUARE'
TT_RSQUARE = 'RSQUARE'
TT_LCURLY = 'LCURLY'
TT_RCURLY = 'RCURLY'
TT_EE = 'EE'
TT_NE = 'NE'
TT_LT = 'LT'
TT_GT = 'GT'
TT_LTE = 'LTE'
TT_GTE = 'GTE'
TT_COMMA = 'COMMA'
TT_COLON = 'COLON'
TT_ARROW = 'ARROW'
TT_QUESTION = 'QUESTION'
TT_NEWLINE = 'NEWLINE'
TT_EOF = 'EOF'

KEYWORDS = [
    'var',
    'let',
    'scoped',
    'strict',
    'and',
    'or',
    'not',
    'if',
    'then',
    'elif',
    'else',
    'for',
    'until',
    'step',
    'while',
    'function',
    'end',
    'return',
    'continue',
    'break'
]

TYPES = [
    'string',
    'int',
    'float'
]


# endregion


class Token:
    def __init__(self, type_, value=None, pos_start=None, pos_end=None):
        self.type = type_
        self.value = value

        if pos_start:
            self.pos_start = pos_start.copy()
            self.pos_end = pos_start.copy()
            self.pos_end.advance()

        if pos_end:
            self.pos_end = pos_end

    def matches(self, type_, value):
        return self.type == type_ and self.value == value

    def __repr__(self):
        if self.value: return f'{self.type}:{self.value}'
        return f'{self.type}'


class Lexer:
    def __init__(self, fn, text):
        self.fn = fn
        self.text = text
        self.pos = Position(-1, 0, -1, fn, text)
        self.current_char = None
        self.previous_char = None
        self.advance()

    def advance(self):
        self.previous_char = self.current_char
        self.pos.advance(self.current_char)
        self.current_char = self.text[self.pos.idx] if self.pos.idx < len(self.text) else None

    def make_tokens(self):
        tokens = []

        while self.current_char is not None:
            if self.current_char in ' \t':
                self.advance()
            elif self.current_char in ';\n':
                tokens.append(Token(TT_NEWLINE, pos_start=self.pos))
                self.advance()
            elif self.current_char == '#':
                self.skip_comment()
            elif self.current_char in DIGITS:
                tokens.append(self.make_number())
            elif self.current_char in LETTERS:
                tokens.append(self.make_identifier())
            elif self.current_char == '"':
                tokens.append(self.make_string())
            elif self.current_char == '+':
                tokens.append(Token(TT_PLUS, pos_start=self.pos))
                self.advance()
            elif self.current_char == '-':
                tokens.append(Token(TT_MINUS, pos_start=self.pos))
                self.advance()
            elif self.current_char == '*':
                tokens.append(Token(TT_MUL, pos_start=self.pos))
                self.advance()
            elif self.current_char == '/':
                tokens.append(Token(TT_DIV, pos_start=self.pos))
                self.advance()
            elif self.current_char == '^':
                tokens.append(Token(TT_POW, pos_start=self.pos))
                self.advance()
            elif self.current_char == '%':
                tokens.append(Token(TT_MOD, pos_start=self.pos))
                self.advance()
            elif self.current_char == '(':
                tokens.append(Token(TT_LPAREN, pos_start=self.pos))
                self.advance()
            elif self.current_char == ')':
                tokens.append(Token(TT_RPAREN, pos_start=self.pos))
                self.advance()
            elif self.current_char == '[':
                tokens.append(Token(TT_LSQUARE, pos_start=self.pos))
                self.advance()
            elif self.current_char == ']':
                tokens.append(Token(TT_RSQUARE, pos_start=self.pos))
                self.advance()
            elif self.current_char == '{':
                tokens.append(Token(TT_LCURLY, pos_start=self.pos))
                self.advance()
            elif self.current_char == '}':
                tokens.append(Token(TT_RCURLY, pos_start=self.pos))
                self.advance()
            elif self.current_char == '!':
                tok, error = self.make_not_equals()
                if error: return [], error
                tokens.append(tok)
            elif self.current_char == '=':
                tokens.append(self.make_equals())
            elif self.current_char == '<':
                tokens.append(self.make_less_than())
            elif self.current_char == '>':
                tokens.append(self.make_greater_than())
            elif self.current_char == ',':
                tokens.append(Token(TT_COMMA, pos_start=self.pos))
                self.advance()
            elif self.current_char == ':':
                tokens.append(Token(TT_COLON, pos_start=self.pos))
                self.advance()
            elif self.current_char == '?':
                tokens.append(Token(TT_QUESTION, pos_start=self.pos))
                self.advance()
            else:
                pos_start = self.pos.copy()
                char = self.current_char
                self.advance()
                return [], IllegalCharError(pos_start, self.pos, "'" + char + "'")

        tokens.append(Token(TT_EOF, pos_start=self.pos))
        return tokens, None

    def make_number(self):
        num_str = ''
        dot_count = 0
        pos_start = self.pos.copy()

        while self.current_char != None and self.current_char in DIGITS + '.':
            if self.current_char == '.':
                if dot_count == 1: break
                dot_count += 1
                num_str += '.'
            else:
                num_str += self.current_char
            self.advance()

        if dot_count == 0:
            return Token(TT_INT, int(num_str), pos_start, self.pos)
        else:
            return Token(TT_FLOAT, float(num_str), pos_start, self.pos)

    def make_string(self):
        string = ''
        pos_start = self.pos.copy()
        escape_character = False
        code = ''
        code_result = None
        self.advance()

        if self.current_char == '$' and self.previous_char != '\\':
            self.advance()
            if self.current_char == '{':
                self.advance()
                while self.current_char != '}':
                    new_code = code + self.current_char
                    code = new_code
                    self.advance()
                self.advance()
                code_result = run_interpolation('INTERPOLATION', code)
                string += str(code_result)

        escape_characters = {
            'n': '\n',
            't': '\t',
            '$': '\$'
        }

        while self.current_char != None and (self.current_char != '"' or escape_character):
            if escape_character:
                string += escape_characters.get(self.current_char, self.current_char)
            else:
                if self.current_char == '\\':
                    escape_character = True
                else:
                    string += self.current_char
            self.advance()
            escape_character = False

            if self.current_char == '$' and self.previous_char != '\\':
                self.advance()
                if self.current_char == '{':
                    self.advance()
                    while self.current_char != '}':
                        new_code = code + self.current_char
                        code = new_code
                        self.advance()
                    self.advance()
                    code_result = run_interpolation('INTERPOLATION', code)
                    string += str(code_result)

        self.advance()
        return Token(TT_STRING, string, pos_start, self.pos)

    def make_identifier(self):
        id_str = ''
        pos_start = self.pos.copy()

        while self.current_char is not None and self.current_char in LETTERS_DIGITS + '_':
            id_str += self.current_char
            self.advance()

        tok_type = TT_KEYWORD if id_str in KEYWORDS else TT_IDENTIFIER
        return Token(tok_type, id_str, pos_start, self.pos)

    def make_not_equals(self):
        pos_start = self.pos.copy()
        self.advance()

        if self.current_char == '=':
            self.advance()
            return Token(TT_NE, pos_start=pos_start, pos_end=self.pos), None

        self.advance()
        return None, ExpectedCharError(pos_start, self.pos, "'=' (after '!')")

    def make_equals(self):
        tok_type = TT_EQ
        pos_start = self.pos.copy()
        self.advance()

        # ==
        if self.current_char == '=':
            self.advance()
            tok_type = TT_EE
        # =>
        elif self.current_char == '>':
            self.advance()
            tok_type = TT_ARROW

        return Token(tok_type, pos_start=pos_start, pos_end=self.pos)

    def make_less_than(self):
        tok_type = TT_LT
        pos_start = self.pos.copy()
        self.advance()

        if self.current_char == '=':
            self.advance()
            tok_type = TT_LTE

        return Token(tok_type, pos_start=pos_start, pos_end=self.pos)

    def make_greater_than(self):
        tok_type = TT_GT
        pos_start = self.pos.copy()
        self.advance()

        if self.current_char == '=':
            self.advance()
            tok_type = TT_GTE

        return Token(tok_type, pos_start=pos_start, pos_end=self.pos)

    def skip_comment(self):
        self.advance()
        while self.current_char != '\n':
            self.advance()
        self.advance()


# region Nodes
class NumberNode:
    def __init__(self, tok):
        self.tok = tok
        self.pos_start = self.tok.pos_start
        self.pos_end = self.tok.pos_end

    def __repr__(self):
        return f'{self.tok}'


class StringNode:
    def __init__(self, tok):
        self.tok = tok
        self.pos_start = self.tok.pos_start
        self.pos_end = self.tok.pos_end

    def __repr__(self):
        return f'{self.tok}'


class ArrayNode:
    def __init__(self, element_nodes, pos_start, pos_end):
        self.element_nodes = element_nodes
        self.pos_start = pos_start
        self.pos_end = pos_end


class VarAssignNode:
    def __init__(self, var_name_tok, value_node):
        self.var_name_tok = var_name_tok
        self.value_node = value_node
        self.pos_start = self.var_name_tok.pos_start
        self.pos_end = self.value_node.pos_end


class ScopedAssignNode:
    def __init__(self, var_name_tok, value_node):
        self.var_name_tok = var_name_tok
        self.value_node = value_node
        self.pos_start = self.var_name_tok.pos_start
        self.pos_end = self.value_node.pos_end


class StrictAssignNode:
    def __init__(self, var_name_tok, value_node, var_type):
        self.var_name_tok = var_name_tok
        self.value_node = value_node
        self.var_type = var_type
        self.pos_start = self.var_name_tok.pos_start
        self.pos_end = self.value_node.pos_end


class AccessNode:
    def __init__(self, var_name_tok):
        self.var_name_tok = var_name_tok
        self.pos_start = self.var_name_tok.pos_start
        self.pos_end = self.var_name_tok.pos_end


class BinaryOpNode:
    def __init__(self, left_node, op_tok, right_node):
        self.left_node = left_node
        self.op_tok = op_tok
        self.right_node = right_node
        self.pos_start = self.left_node.pos_start
        self.pos_end = self.right_node.pos_end

    def __repr__(self):
        return f'({self.left_node}, {self.op_tok}, {self.right_node})'


class UnaryOpNode:
    def __init__(self, op_tok, node):
        self.op_tok = op_tok
        self.node = node
        self.pos_start = self.op_tok.pos_start
        self.pos_end = node.pos_end

    def __repr__(self):
        return f'({self.op_tok}, {self.node})'


class IfNode:
    def __init__(self, cases, else_case):
        self.cases = cases
        self.else_case = else_case
        self.pos_start = self.cases[0][0].pos_start
        self.pos_end = (self.else_case or self.cases[len(self.cases) - 1])[0].pos_end


class ForNode:
    def __init__(self, var_name_tok, start_value_node, end_value_node, step_value_node, body_node, should_return_null):
        self.var_name_tok = var_name_tok
        self.start_value_node = start_value_node
        self.end_value_node = end_value_node
        self.step_value_node = step_value_node
        self.body_node = body_node
        self.should_return_null = should_return_null

        self.pos_start = self.var_name_tok.pos_start
        self.pos_end = self.body_node.pos_end


class WhileNode:
    def __init__(self, condition_node, body_node, should_return_null):
        self.condition_node = condition_node
        self.body_node = body_node
        self.should_return_null = should_return_null

        self.pos_start = self.condition_node.pos_start
        self.pos_end = self.body_node.pos_end


class FuncDefNode:
    def __init__(self, var_name_tok, arg_name_toks, arg_defaults, body_node, should_auto_return):
        self.var_name_tok = var_name_tok
        self.arg_name_toks = arg_name_toks
        self.arg_defaults = arg_defaults
        self.body_node = body_node
        self.should_auto_return = should_auto_return

        if self.var_name_tok:
            self.pos_start = self.var_name_tok.pos_start
        elif len(self.arg_name_toks) > 0:
            self.pos_start = self.arg_name_toks[0].pos_start
        else:
            self.pos_start = self.body_node.pos_start

        self.pos_end = self.body_node.pos_end


class CallNode:
    def __init__(self, node_to_call, arg_nodes):
        self.node_to_call = node_to_call
        self.arg_nodes = arg_nodes

        self.pos_start = self.node_to_call.pos_start

        if len(self.arg_nodes) > 0:
            self.pos_end = self.arg_nodes[len(self.arg_nodes) - 1].pos_end
        else:
            self.pos_end = self.node_to_call.pos_end


class ReturnNode:
    def __init__(self, node_to_return, pos_start, pos_end):
        self.node_to_return = node_to_return
        self.pos_start = pos_start
        self.pos_end = pos_end


class ContinueNode:
    def __init__(self, pos_start, pos_end):
        self.pos_start = pos_start
        self.pos_end = pos_end


class BreakNode:
    def __init__(self, pos_start, pos_end):
        self.pos_start = pos_start
        self.pos_end = pos_end


# endregion


class ParseResult:
    def __init__(self):
        self.error = None
        self.node = None
        self.advance_count = 0
        self.to_reverse_count = 0

    def register(self, res):
        self.advance_count += res.advance_count
        if res.error: self.error = res.error
        return res.node

    def try_register(self, res):
        if res.error:
            self.to_reverse_count = res.advance_count
            return None
        return self.register(res)

    def register_advancement(self):
        self.advance_count += 1

    def success(self, node):
        self.node = node
        return self

    def failure(self, error):
        if not self.error or self.advance_count == 0:
            self.error = error
        return self

    def should_return(self):
        return self.error


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.tok_idx = -1
        self.advance()

    def advance(self):
        self.tok_idx += 1
        self.update_current_tok()
        return self.current_tok

    def reverse(self, amount=1):
        self.tok_idx -= amount
        self.update_current_tok()
        return self.current_tok

    def update_current_tok(self):
        if self.tok_idx >= 0 and self.tok_idx < len(self.tokens):
            self.current_tok = self.tokens[self.tok_idx]

    def parse(self):
        res = self.statements()
        if not res.error and self.current_tok.type != TT_EOF:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                "Token cannot appear after previous tokens"
            ))
        return res

    def atom(self):
        res = ParseResult()
        tok = self.current_tok

        if tok.type in (TT_INT, TT_FLOAT):
            res.register_advancement()
            self.advance()
            return res.success(NumberNode(tok))

        elif tok.type == TT_STRING:
            res.register_advancement()
            self.advance()
            return res.success(StringNode(tok))

        elif tok.type == TT_IDENTIFIER:
            res.register_advancement()
            self.advance()
            return res.success(AccessNode(tok))

        elif tok.type == TT_LPAREN:
            res.register_advancement()
            self.advance()
            expression = res.register(self.expression())
            if res.error: return res
            if self.current_tok.type == TT_RPAREN:
                res.register_advancement()
                self.advance()
                return res.success(expression)
            else:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected ')'"
                ))

        elif tok.type == TT_LSQUARE:
            list_expr = res.register(self.list_expr())
            if res.error: return res
            return res.success(list_expr)

        # elif tok.type == TT_LCURLY:
        #    list_expr = res.register(self.obj_expr())
        #    if res.error: return res
        #    return res.success(list_expr)

        elif tok.matches(TT_KEYWORD, 'if'):
            if_expr = res.register(self.if_expr())
            if res.error: return res
            return res.success(if_expr)

        elif tok.matches(TT_KEYWORD, 'for'):
            for_expr = res.register(self.for_expr())
            if res.error: return res
            return res.success(for_expr)

        elif tok.matches(TT_KEYWORD, 'while'):
            while_expr = res.register(self.while_expr())
            if res.error: return res
            return res.success(while_expr)

        elif tok.matches(TT_KEYWORD, 'function'):
            func = res.register(self.func_def())
            if res.error: return res
            return res.success(func)

        return res.failure(InvalidSyntaxError(
            tok.pos_start, tok.pos_end,
            "Expected ')', 'var', 'if', 'function', int, float, identifier, '+', '-', '(', '[', or 'not' "
        ))

    def func_def(self):
        res = ParseResult()

        if not self.current_tok.matches(TT_KEYWORD, 'function'):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'function'"
            ))

        res.register_advancement()
        self.advance()

        if self.current_tok.type == TT_IDENTIFIER:
            var_name_tok = self.current_tok
            res.register_advancement()
            self.advance()
            if self.current_tok.type != TT_LPAREN:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    f"Expected '('"
                ))
        else:
            var_name_tok = None
            if self.current_tok.type != TT_LPAREN:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    f"Expected identifier or '('"
                ))

        res.register_advancement()
        self.advance()
        arg_name_toks = []
        arg_defaults = []

        if self.current_tok.type == TT_IDENTIFIER:
            arg_name_toks.append(self.current_tok)
            res.register_advancement()
            self.advance()

            if self.current_tok.type == TT_EQ:
                res.register_advancement()
                self.advance()
                arg_defaults.append(self.current_tok)
                res.register_advancement()
                self.advance()
                has_made_mandatory_arg = True

            while self.current_tok.type == TT_COMMA:
                res.register_advancement()
                self.advance()

                if self.current_tok.type != TT_IDENTIFIER:
                    return res.failure(InvalidSyntaxError(
                        self.current_tok.pos_start, self.current_tok.pos_end,
                        f"Expected identifier"
                    ))

                arg_name_toks.append(self.current_tok)
                res.register_advancement()
                self.advance()

            if self.current_tok.type == TT_EQ:
                res.register_advancement()
                self.advance()
                arg_defaults.append(self.current_tok)
                has_made_mandatory_arg = True
                res.register_advancement()
                self.advance()

            if self.current_tok.type != TT_RPAREN:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    f"Expected ',' '=' or ')'"
                ))
        else:
            if self.current_tok.type != TT_RPAREN:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    f"Expected identifier or ')'"
                ))

        res.register_advancement()
        self.advance()

        if self.current_tok.type == TT_ARROW:
            res.register_advancement()
            self.advance()
            node_to_return = res.register(self.expression())
            if res.error: return res

            return res.success(FuncDefNode(
                var_name_tok,
                arg_name_toks,
                arg_defaults,
                node_to_return,
                True
            ))

        if self.current_tok.type != TT_NEWLINE:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected '=>' or NEWLINE"
            ))

        res.register_advancement()
        self.advance()

        body = res.register(self.statements())
        if res.error: return res

        if not self.current_tok.matches(TT_KEYWORD, 'end'):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'end'"
            ))

        res.register_advancement()
        self.advance()

        return res.success(FuncDefNode(
            var_name_tok,
            arg_name_toks,
            arg_defaults,
            body,
            False
        ))

    def call(self):
        res = ParseResult()
        atom = res.register(self.atom())
        if res.error: return res

        if self.current_tok.type == TT_LPAREN:
            res.register_advancement()
            self.advance()
            arg_nodes = []

            if self.current_tok.type == TT_RPAREN:
                res.register_advancement()
                self.advance()
            else:
                arg_nodes.append(res.register(self.expression()))
                if res.error:
                    return res.failure(InvalidSyntaxError(
                        self.current_tok.pos_start, self.current_tok.pos_end,
                        "Expected ')', 'var', 'if', 'function', int, float, identifier, '+', '-', '(', '[', or 'not' "
                    ))

                while self.current_tok.type == TT_COMMA:
                    res.register_advancement()
                    self.advance()

                    arg_nodes.append(res.register(self.expression()))
                    if res.error: return res

                if self.current_tok.type != TT_RPAREN:
                    return res.failure(InvalidSyntaxError(
                        self.current_tok.pos_start, self.current_tok.pos_end,
                        f"Expected ',' or ')'"
                    ))

                res.register_advancement()
                self.advance()
            return res.success(CallNode(atom, arg_nodes))
        return res.success(atom)

    def for_expr(self):
        res = ParseResult()

        if not self.current_tok.matches(TT_KEYWORD, 'for'):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'for'"
            ))

        res.register_advancement()
        self.advance()

        if self.current_tok.type != TT_IDENTIFIER:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected identifier"
            ))

        var_name = self.current_tok
        res.register_advancement()
        self.advance()

        if self.current_tok.type != TT_EQ:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected '='"
            ))

        res.register_advancement()
        self.advance()

        start_value = res.register(self.expression())
        if res.error: return res

        if not self.current_tok.matches(TT_KEYWORD, 'until'):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'until'"
            ))

        res.register_advancement()
        self.advance()

        end_value = res.register(self.expression())
        if res.error: return res

        if self.current_tok.matches(TT_KEYWORD, 'step'):
            res.register_advancement()
            self.advance()

            step_value = res.register(self.expression())
            if res.error: return res
        else:
            step_value = None

        if not (self.current_tok.matches(TT_KEYWORD, 'then') or self.current_tok.type == 'ARROW'):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'then' or '=>'"
            ))

        res.register_advancement()
        self.advance()

        if self.current_tok.type == TT_NEWLINE:
            res.register_advancement()
            self.advance()

            body = res.register(self.statements())
            if res.error: return res

            if not self.current_tok.matches(TT_KEYWORD, 'end'):
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    f"Expected 'end'"
                ))

            res.register_advancement()
            self.advance()

            return res.success(ForNode(var_name, start_value, end_value, step_value, body, True))

        body = res.register(self.statement())
        if res.error: return res

        return res.success(ForNode(var_name, start_value, end_value, step_value, body, False))

    def while_expr(self):
        res = ParseResult()

        if not self.current_tok.matches(TT_KEYWORD, 'while'):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'while'"
            ))

        res.register_advancement()
        self.advance()

        condition = res.register(self.expression())
        if res.error: return res

        if not (self.current_tok.matches(TT_KEYWORD, 'then') or self.current_tok.type == 'ARROW'):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'then' or '=>'"
            ))

        res.register_advancement()
        self.advance()

        if self.current_tok.type == TT_NEWLINE:
            res.register_advancement()
            self.advance()

            body = res.register(self.statements())
            if res.error: return res

            if not self.current_tok.matches(TT_KEYWORD, 'end'):
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    f"Expected 'end'"
                ))

            res.register_advancement()
            self.advance()

            return res.success(WhileNode(condition, body, True))

        body = res.register(self.statement())
        if res.error: return res

        return res.success(WhileNode(condition, body, False))

    def if_expr(self):
        res = ParseResult()
        all_cases = res.register(self.if_expr_cases('if'))
        if res.error: return res
        cases, else_case = all_cases
        return res.success(IfNode(cases, else_case))

    def if_expr_b(self):
        return self.if_expr_cases('elif')

    def if_expr_c(self):
        res = ParseResult()
        else_case = None

        if self.current_tok.matches(TT_KEYWORD, 'else'):
            res.register_advancement()
            self.advance()

            if self.current_tok.type == TT_NEWLINE:
                res.register_advancement()
                self.advance()

                statements = res.register(self.statements())
                if res.error: return res
                else_case = (statements, True)

                if self.current_tok.matches(TT_KEYWORD, 'end'):
                    res.register_advancement()
                    self.advance()
                else:
                    return res.failure(InvalidSyntaxError(
                        self.current_tok.pos_start, self.current_tok.pos_end,
                        "Expected 'end'"
                    ))
            else:
                expr = res.register(self.statement())
                if res.error: return res
                else_case = (expr, False)

        return res.success(else_case)

    def if_expr_b_or_c(self):
        res = ParseResult()
        cases, else_case = [], None

        if self.current_tok.matches(TT_KEYWORD, 'elif'):
            all_cases = res.register(self.if_expr_b())
            if res.error: return res
            cases, else_case = all_cases
        else:
            else_case = res.register(self.if_expr_c())
            if res.error: return res

        return res.success((cases, else_case))

    def if_expr_cases(self, case_keyword):
        res = ParseResult()
        cases = []
        else_case = None

        if not self.current_tok.matches(TT_KEYWORD, case_keyword):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected '{case_keyword}'"
            ))

        res.register_advancement()
        self.advance()

        condition = res.register(self.expression())
        if res.error: return res

        if not (self.current_tok.matches(TT_KEYWORD, 'then') or self.current_tok.type == TT_ARROW):
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected 'then' or '=>'"
            ))

        res.register_advancement()
        self.advance()

        if self.current_tok.type == TT_NEWLINE:
            res.register_advancement()
            self.advance()

            statements = res.register(self.statements())
            if res.error: return res
            cases.append((condition, statements, True))

            if self.current_tok.matches(TT_KEYWORD, 'end'):
                res.register_advancement()
                self.advance()
            else:
                all_cases = res.register(self.if_expr_b_or_c())
                if res.error: return res
                new_cases, else_case = all_cases
                cases.extend(new_cases)
        else:
            expr = res.register(self.statement())
            if res.error: return res
            cases.append((condition, expr, False))

            all_cases = res.register(self.if_expr_b_or_c())
            if res.error: return res
            new_cases, else_case = all_cases
            cases.extend(new_cases)

        return res.success((cases, else_case))

    def power(self):
        return self.BinaryOp(self.call, (TT_POW,), self.factor)

    def factor(self):
        res = ParseResult()
        tok = self.current_tok

        if tok.type in (TT_PLUS, TT_MINUS):
            res.register_advancement()
            self.advance()
            factor = res.register(self.factor())
            if res.error: return res
            return res.success(UnaryOpNode(tok, factor))

        return self.power()

    def term(self):
        return self.BinaryOp(self.factor, (TT_MUL, TT_DIV, TT_MOD))

    def arith_expr(self):
        return self.BinaryOp(self.term, (TT_PLUS, TT_MINUS))

    def comp_expr(self):
        res = ParseResult()
        if self.current_tok.matches(TT_KEYWORD, 'not'):
            op_tok = self.current_tok
            res.register_advancement()
            self.advance()

            node = res.register(self.comp_expr())
            if res.error: return res
            return res.success(UnaryOpNode(op_tok, node))
        node = res.register(self.BinaryOp(self.arith_expr, (TT_EE, TT_NE, TT_LT, TT_GT, TT_LTE, TT_GTE)))
        if res.error:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                "Expected var, if, function, Int, Float, Identifier, '+', '-', '(', '[', or 'not'"
            ))

        return res.success(node)

    def list_expr(self):
        res = ParseResult()
        element_nodes = []
        pos_start = self.current_tok.pos_start.copy()

        if self.current_tok.type != TT_LSQUARE:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                f"Expected '['"
            ))

        res.register_advancement()
        self.advance()

        if self.current_tok.type == TT_RSQUARE:
            res.register_advancement()
            self.advance()
        else:
            element_nodes.append(res.register(self.expression()))
            if res.error:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected ']', 'var', 'if', 'function', int, float, identifier, '+', '-', '(', '[', or 'not' "
                ))

            while self.current_tok.type == TT_COMMA:
                res.register_advancement()
                self.advance()

                element_nodes.append(res.register(self.expression()))
                if res.error: return res

            if self.current_tok.type != TT_RSQUARE:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    f"Expected ',' or ']'"
                ))

            res.register_advancement()
            self.advance()

        return res.success(ArrayNode(
            element_nodes,
            pos_start,
            self.current_tok.pos_end.copy()
        ))

    def statements(self):
        res = ParseResult()
        statements = []
        pos_start = self.current_tok.pos_start.copy()

        while self.current_tok.type == TT_NEWLINE:
            res.register_advancement()
            self.advance()

        statement = res.register(self.statement())
        if res.error: return res
        statements.append(statement)

        more_statements = True

        while True:
            newline_count = 0
            while self.current_tok.type == TT_NEWLINE:
                res.register_advancement()
                self.advance()
                newline_count += 1
            if newline_count == 0:
                more_statements = False

            if not more_statements: break
            statement = res.try_register(self.statement())
            if not statement:
                self.reverse(res.to_reverse_count)
                more_statements = False
                continue
            statements.append(statement)

        return res.success(ArrayNode(
            statements,
            pos_start,
            self.current_tok.pos_end.copy()
        ))

    def statement(self):
        res = ParseResult()
        pos_start = self.current_tok.pos_start.copy()

        if self.current_tok.matches(TT_KEYWORD, 'return'):
            res.register_advancement()
            self.advance()

            expr = res.try_register(self.expression())
            if not expr:
                self.reverse(res.to_reverse_count)
            return res.success(ReturnNode(expr, pos_start, self.current_tok.pos_start.copy()))

        if self.current_tok.matches(TT_KEYWORD, 'continue'):
            res.register_advancement()
            self.advance()
            return res.success(ContinueNode(pos_start, self.current_tok.pos_start.copy()))

        if self.current_tok.matches(TT_KEYWORD, 'break'):
            res.register_advancement()
            self.advance()
            return res.success(BreakNode(pos_start, self.current_tok.pos_start.copy()))

        expr = res.register(self.expression())
        if res.error:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                "Expected 'return', 'continue', 'break', 'var', 'if', 'for', 'while', 'function', int, float, "
                "identifier, '+', '-', '(', '[' or 'not' "
            ))
        return res.success(expr)

    def expression(self):
        res = ParseResult()
        possible_ops = [TT_EQ, TT_PLUS, TT_MINUS, TT_MUL, TT_DIV, TT_MOD, TT_POW]

        if self.current_tok.matches(TT_KEYWORD, 'var') or self.current_tok.matches(TT_KEYWORD, 'let'):
            res.register_advancement()
            self.advance()

            if self.current_tok.type != TT_IDENTIFIER:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected identifier"
                ))

            var_name = self.current_tok
            res.register_advancement()
            self.advance()

            if self.current_tok.type != TT_EQ:
                return res.success(VarAssignNode(var_name, Number.null))

            res.register_advancement()
            self.advance()
            expr = res.register(self.expression())
            if res.error: return res
            return res.success(VarAssignNode(var_name, expr))

        if self.current_tok.matches(TT_KEYWORD, 'scoped'):
            res.register_advancement()
            self.advance()

            if self.current_tok.type != TT_IDENTIFIER:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected identifier"
                ))

            var_name = self.current_tok
            res.register_advancement()
            self.advance()

            if self.current_tok.type != TT_EQ:
                return res.success(VarAssignNode(var_name, Number.null))

            res.register_advancement()
            self.advance()
            expr = res.register(self.expression())
            if res.error: return res
            return res.success(ScopedAssignNode(var_name, expr))

        if self.current_tok.matches(TT_KEYWORD, 'strict'):
            res.register_advancement()
            self.advance()

            if self.current_tok.value not in TYPES:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected Type declaration"
                ))
            type_ = self.current_tok.value
            res.register_advancement()
            self.advance()

            if self.current_tok.type != TT_IDENTIFIER:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected identifier"
                ))

            var_name = self.current_tok
            clean_var_name = str(var_name).replace('IDENTIFIER:', '')
            if global_symbol_table.isStrict(clean_var_name):
                if type_ != global_symbol_table.getType(clean_var_name):
                    return res.failure(InvalidSyntaxError(
                        self.current_tok.pos_start, self.current_tok.pos_end,
                        "Cannot assign 'strict' variable to different type!"
                    ))
            res.register_advancement()
            self.advance()

            if self.current_tok.type != TT_EQ:
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected '='"
                ))

            res.register_advancement()
            self.advance()
            expr = res.register(self.expression())

            if type_ == "string" and not str(expr).__contains__('STRING'):
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected Type 'string'"
                ))

            if type_ == "int" and not str(expr).__contains__('INT'):
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected Type 'int'"
                ))

            if type_ == "float" and not str(expr).__contains__('FLOAT'):
                return res.failure(InvalidSyntaxError(
                    self.current_tok.pos_start, self.current_tok.pos_end,
                    "Expected Type 'float'"
                ))

            if res.error: return res
            return res.success(StrictAssignNode(var_name, expr, type_))

        node = res.register(self.BinaryOp(self.comp_expr, ((TT_KEYWORD, 'and'), (TT_KEYWORD, 'or'))))

        if res.error:
            return res.failure(InvalidSyntaxError(
                self.current_tok.pos_start, self.current_tok.pos_end,
                "Expected 'var', 'let', 'if', 'for', 'while', 'function', int, float, identifier, '+', '-', '(', '[' or 'not'"
            ))

        return res.success(node)

    def BinaryOp(self, func_a, ops, func_b=None):
        if func_b is None:
            func_b = func_a
        res = ParseResult()
        left = res.register(func_a())
        if res.error: return res

        while self.current_tok.type in ops or (self.current_tok.type, self.current_tok.value) in ops:
            op_tok = self.current_tok
            res.register_advancement()
            self.advance()
            right = res.register(func_b())
            if res.error: return res
            left = BinaryOpNode(left, op_tok, right)

        return res.success(left)


class RTResult:
    def __init__(self):
        self.value = None
        self.error = None
        self.warn = None
        self.func_return_value = None
        self.loop_should_continue = False
        self.loop_should_break = False
        # self.no_return_value = False
        self.to_reverse_count = 0
        self.reset()

    def reset(self):
        self.value = None
        self.error = None
        self.func_return_value = None
        self.loop_should_continue = False
        self.loop_should_break = False
        self.to_reverse_count = 0

    def register(self, res):
        self.error = res.error
        self.func_return_value = res.func_return_value
        self.loop_should_continue = res.loop_should_continue
        self.loop_should_break = res.loop_should_break
        return res.value

    def try_register(self, res):
        if res.error:
            self.to_reverse_count = res.advance_count
            return None
        return self.register(res)

    def success(self, value=None):
        self.reset()
        self.value = value
        return self

    def success_return(self, value):
        self.reset()
        self.func_return_value = value
        return self

    def success_continue(self):
        self.reset()
        self.loop_should_continue = True
        return self

    def success_break(self):
        self.reset()
        self.loop_should_break = True
        return self

    def failure(self, error):
        self.reset()
        self.error = error
        return self

    def warn(self, warn):
        self.warn = warn

    def should_return(self):
        return (
                self.error or self.func_return_value or self.loop_should_continue or self.loop_should_break
        )


# region Data Types
class Value:
    def __init__(self):
        self.set_pos()
        self.set_context()

    def set_pos(self, pos_start=None, pos_end=None):
        self.pos_start = pos_start
        self.pos_end = pos_end
        return self

    def set_context(self, context=None):
        self.context = context
        return self

    def added_to(self, other):
        return None, self.illegal_operation(other)

    def subbed_by(self, other):
        return None, self.illegal_operation(other)

    def multed_by(self, other):
        return None, self.illegal_operation(other)

    def dived_by(self, other):
        return None, self.illegal_operation(other)

    def powed_by(self, other):
        return None, self.illegal_operation(other)

    def modded(self, other):
        return None, self.illegal_operation(other)

    def get_comparison_eq(self, other):
        return None, self.illegal_operation(other)

    def get_comparison_ne(self, other):
        return None, self.illegal_operation(other)

    def get_comparison_lt(self, other):
        return None, self.illegal_operation(other)

    def get_comparison_gt(self, other):
        return None, self.illegal_operation(other)

    def get_comparison_lte(self, other):
        return None, self.illegal_operation(other)

    def get_comparison_gte(self, other):
        return None, self.illegal_operation(other)

    def anded_by(self, other):
        return None, self.illegal_operation(other)

    def ored_by(self, other):
        return None, self.illegal_operation(other)

    def notted(self, other):
        if other:
            return None, self.illegal_operation(other)
        else:
            return None, self.illegal_operation(self)

    def execute(self, args):
        return RTResult().failure(self.illegal_operation())

    def copy(self):
        raise Exception('No copy method defined')

    def is_true(self):
        return False

    def illegal_operation(self, other=None):
        if not other: other = self
        return RTError(
            self.pos_start, other.pos_end,
            'Illegal operation',
            self.context
        )


class Number(Value):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def added_to(self, other):
        if isinstance(other, Number):
            return Number(self.value + other.value).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def subtracted_by(self, other):
        if isinstance(other, Number):
            return Number(self.value - other.value).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def multiplied_by(self, other):
        if isinstance(other, Number):
            return Number(self.value * other.value).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def divided_by(self, other):
        if isinstance(other, Number):
            if other.value == 0:
                return None, RTError(
                    other.pos_start, other.pos_end,
                    'Division by zero',
                    self.context
                )
            return Number(self.value / other.value).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def modded_by(self, other):
        if isinstance(other, Number):
            if other.value == 0:
                return None, RTError(
                    other.pos_start, other.pos_end,
                    'Division by zero',
                    self.context
                )
            return Number(self.value - (other.value * floor(self.value / other.value))).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def pow(self, other):
        if isinstance(other, Number):
            return Number(self.value ** other.value).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def get_comparison_eq(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value == other.value)).set_context(self.context), None
        else:
            return Bool(0).set_context(self.context), None

    def get_comparison_ne(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value != other.value)).set_context(self.context), None
        else:
            return Bool(1).set_context(self.context), None

    def get_comparison_lt(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value < other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def get_comparison_gt(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value > other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def get_comparison_lte(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value <= other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def get_comparison_gte(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value >= other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def anded_by(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value and other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def ored_by(self, other):
        if isinstance(other, Number):
            return Bool(int(self.value or other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def notted(self, other=None):
        return Bool(1 if self.value == 0 else 0).set_context(self.context), None

    def copy(self):
        copy = Number(self.value)
        copy.set_pos(self.pos_start, self.pos_end)
        copy.set_context(self.context)
        return copy

    def is_true(self):
        return self.value != 0

    def __int__(self):
        return int(self.value)

    def __float__(self):
        return float(self.value)

    def __repr__(self):
        return str(self.value)


Number.null = Number(0)
Number.false = Number(0)
Number.true = Number(1)
Number.infinity = Number(float('inf'))
Number.negative_infinity = Number(float('-inf'))


class String(Value):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def added_to(self, other):
        if isinstance(other, String):
            return String(self.value + other.value).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def multed_by(self, other):
        if isinstance(other, Number):
            return String(self.value * other.value).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def divided_by(self, other):
        if isinstance(other, Number):
            try:
                return String(self.value[other.value]).set_context(self.context), None
            except:
                return None, RTError(
                    other.pos_start, other.pos_end,
                    'Character at this index could not be obtained because the index is out of bounds',
                    self.context
                )
        else:
            return None, Value.illegal_operation(self, other)

    def get_comparison_eq(self, other):
        if isinstance(other, String):
            return Bool(int(self.value == other.value)).set_context(self.context), None
        else:
            return Bool(0).set_context(self.context), None

    def get_comparison_ne(self, other):
        if isinstance(other, String):
            return Bool(int(self.value != other.value)).set_context(self.context), None
        else:
            return Bool(1).set_context(self.context), None

    def is_true(self):
        return len(self.value) > 0

    def copy(self):
        copy = String(self.value)
        copy.set_pos(self.pos_start, self.pos_end)
        copy.set_context(self.context)
        return copy

    def display_without_quotes(self):
        return self.value

    def __getitem__(self, items):
        return type(items), items

    def __len__(self):
        count = 0
        for i in self.value:
            count += 1
        return count

    def __str__(self):
        return self.value

    def __repr__(self):
        if self.value != "No Return Value, ignore this!":
            return f'"{self.value}"'
        else:
            return self.value


String.no_return = String("No Return Value, ignore this!")


class Array(Value):
    def __init__(self, elements):
        super().__init__()
        self.elements = elements

    def added_to(self, other):
        new_list = self.copy()
        new_list.elements.append(other)
        return new_list, None

    def subtracted_by(self, other):
        if isinstance(other, Number):
            new_list = self.copy()
            try:
                new_list.elements.pop(other.value)
                return new_list, None
            except:
                return None, RTError(
                    other.pos_start, other.pos_end,
                    'Element at this index could not be removed because the index is out of bounds',
                    self.context
                )
        else:
            return None, Value.illegal_operation(self, other)

    def multiplied_by(self, other):
        if isinstance(other, Array):
            new_list = self.copy()
            new_list.elements.extend(other.elements)
            return new_list, None
        else:
            return None, Value.illegal_operation(self, other)

    def divided_by(self, other):
        if isinstance(other, Number):
            try:
                return self.elements[other.value], None
            except:
                return None, RTError(
                    other.pos_start, other.pos_end,
                    'Element at this index could not be obtained because the index is out of bounds',
                    self.context
                )
        else:
            return None, Value.illegal_operation(self, other)

    def copy(self):
        copy = Array(self.elements)
        copy.set_pos(self.pos_start, self.pos_end)
        copy.set_context(self.context)
        return copy

    def __str__(self):
        return ", ".join([str(x) for x in self.elements])

    def __repr__(self):
        return f'[{", ".join([str(x) for x in self.elements])}]'


class Bool(Value):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def get_comparison_eq(self, other):
        if isinstance(other, Bool):
            return Bool(int(self.value == other.value)).set_context(self.context), None
        else:
            return Bool(0).set_context(self.context), None

    def get_comparison_ne(self, other):
        if isinstance(other, Bool):
            return Bool(int(self.value != other.value)).set_context(self.context), None
        else:
            return Bool(1).set_context(self.context), None

    def anded_by(self, other):
        if isinstance(other, Bool):
            return Bool(int(self.value and other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def ored_by(self, other):
        if isinstance(other, Bool):
            return Bool(int(self.value or other.value)).set_context(self.context), None
        else:
            return None, Value.illegal_operation(self, other)

    def notted(self, other=None):
        return Bool(1 if self.value == 0 else 0).set_context(self.context), None

    def is_true(self):
        return self.value == 1

    def copy(self):
        copy = Bool(self.value)
        copy.set_pos(self.pos_start, self.pos_end)
        copy.set_context(self.context)
        return copy

    def __repr__(self):
        if self.value == 1:
            return str('True')
        else:
            return str('False')


class BaseFunction(Value):
    def __init__(self, name):
        super().__init__()
        self.name = name or "<anonymous>"

    def generate_new_context(self):
        new_context = Context(self.name, self.context, self.pos_start)
        new_context.symbol_table = SymbolTable(new_context.parent.symbol_table)
        return new_context

    def check_args(self, arg_names, arg_defaults, args):
        res = RTResult()

        if len(args) > len(arg_names):
            return res.failure(RTError(
                self.pos_start, self.pos_end,
                f"{len(args) - len(arg_names)} too many args passed into {self}",
                self.context
            ))

        if (len(args) < len(arg_names)) and (len(args) > len(arg_defaults)):
            return res.failure(RTError(
                self.pos_start, self.pos_end,
                f"{len(arg_names) - len(args)} too few args passed into {self}",
                self.context
            ))

        return res.success(None)

    def populate_args(self, arg_names, arg_defaults, args, exec_ctx):
        if arg_defaults is not None:
            if len(arg_defaults) != 0:
                has_defaults = True
            else:
                has_defaults = False
        else:
            has_defaults = False
        chosen = arg_defaults if has_defaults else args
        for i in range(len(chosen)):
            arg_name = arg_names[i]
            if (len(args) < i) or (len(args) == 0):
                if str(arg_defaults[i]).__contains__("INT:"):
                    fixed = str(arg_defaults[i]).replace("INT:", '')
                elif str(arg_defaults[i]).__contains__("STRING:"):
                    fixed = str(arg_defaults[i]).replace("STRING:", '')
                else:
                    fixed = str(arg_defaults[i]).replace("FLOAT:", '')
                arg_value = Number(fixed)
                arg_value.set_context(exec_ctx)
            else:
                arg_value = args[i]
                arg_value.set_context(exec_ctx)
            exec_ctx.symbol_table.set(arg_name, arg_value)

    def check_and_populate_args(self, arg_names, arg_defaults, args, exec_ctx):
        res = RTResult()
        res.register(self.check_args(arg_names, arg_defaults, args))
        if res.should_return(): return res
        self.populate_args(arg_names, arg_defaults, args, exec_ctx)
        return res.success(None)


class Function(BaseFunction):
    def __init__(self, name, body_node, arg_names, arg_defaults, should_auto_return):
        super().__init__(name)
        self.body_node = body_node
        self.arg_names = arg_names
        self.arg_defaults = arg_defaults
        self.should_auto_return = should_auto_return

    def execute(self, args):
        res = RTResult()
        interpreter = Interpreter()
        exec_ctx = self.generate_new_context()

        res.register(self.check_and_populate_args(self.arg_names, self.arg_defaults, args, exec_ctx))
        if res.should_return(): return res

        value = res.register(interpreter.visit(self.body_node, exec_ctx))
        if res.should_return() and res.func_return_value is None: return res

        ret_value = (value if self.should_auto_return else None) or res.func_return_value or Number.null
        return res.success(ret_value)

    def copy(self):
        copy = Function(self.name, self.body_node, self.arg_names, self.arg_defaults, self.should_auto_return)
        copy.set_context(self.context)
        copy.set_pos(self.pos_start, self.pos_end)
        return copy

    def __repr__(self):
        return f"<function {self.name}>"


class BuiltInFunction(BaseFunction):
    def __init__(self, name):
        super().__init__(name)

    def execute(self, args):
        res = RTResult()
        exec_ctx = self.generate_new_context()

        method_name = f'execute_{self.name}'
        method = getattr(self, method_name, self.no_visit_method)

        res.register(self.check_and_populate_args(method.arg_names, None, args, exec_ctx))
        if res.should_return(): return res

        return_value = res.register(method(exec_ctx))
        if res.should_return(): return res
        return res.success(return_value)

    def no_visit_method(self):
        raise Exception(f'No execute_${self.name} method defined')

    def copy(self):
        copy = BuiltInFunction(self.name)
        copy.set_context(self.context)
        copy.set_pos(self.pos_start, self.pos_end)
        return copy

    def __repr__(self):
        return f'<built-in ${self.name}>'

    def execute_print(self, exec_ctx):
        if type(exec_ctx.symbol_table.get('value')) is Array:
            return RTResult().success(String(f"[{str(exec_ctx.symbol_table.get('value'))}]"))
        else:
            return RTResult().success(String(exec_ctx.symbol_table.get('value')))

    execute_print.arg_names = ["value"]

    def execute_input(self, exec_ctx):
        text = input()
        return RTResult().success(String(text))

    execute_input.arg_names = []

    def execute_input_int(self, exec_ctx):
        while True:
            text = input()
            if not containsAny(text, LETTERS):
                number = Number(text)
                break
            else:
                print(f"Input must be a Number!")
        return RTResult().success(number)

    execute_input_int.arg_names = []

    def execute_clear(self, exec_ctx):
        os.system('cls' if os.name == 'windows' else 'clear')
        return RTResult().success(String.no_return)

    execute_clear.arg_names = []

    def execute_is_number(self, exec_ctx):
        is_number = isinstance(exec_ctx.symbol_table.get('value'), Number)
        return RTResult().success(Number.true if is_number else Number.false)

    execute_is_number.arg_names = ['value']

    def execute_is_string(self, exec_ctx):
        is_number = isinstance(exec_ctx.symbol_table.get('value'), String)
        return RTResult().success(Number.true if is_number else Number.false)

    execute_is_string.arg_names = ['value']

    def execute_is_array(self, exec_ctx):
        is_number = isinstance(exec_ctx.symbol_table.get('value'), Array)
        return RTResult().success(Number.true if is_number else Number.false)

    execute_is_array.arg_names = ['value']

    def execute_is_function(self, exec_ctx):
        is_number = isinstance(exec_ctx.symbol_table.get('value'), BaseFunction)
        return RTResult().success(Number.true if is_number else Number.false)

    execute_is_function.arg_names = ['value']

    def execute_typeof(self, exec_ctx):
        is_number = isinstance(exec_ctx.symbol_table.get('value'), Number)
        is_string = isinstance(exec_ctx.symbol_table.get('value'), String)
        is_array = isinstance(exec_ctx.symbol_table.get('value'), Array)
        is_function = isinstance(exec_ctx.symbol_table.get('value'), BaseFunction)
        is_bool = isinstance(exec_ctx.symbol_table.get('value'), Bool)
        if is_number:
            return RTResult().success(String("Number"))
        elif is_string:
            return RTResult().success(String("String"))
        elif is_array:
            return RTResult().success(String("Array"))
        elif is_function:
            return RTResult().success(String("Function"))
        elif is_bool:
            return RTResult().success(String("Bool"))
        else:
            return RTResult().success(String("That's strange, this value has no type."))

    execute_typeof.arg_names = ['value']

    def execute_len(self, exec_ctx):
        array_ = exec_ctx.symbol_table.get('array')
        if isinstance(array_, Array):
            return RTResult().success(Number(len(array_.elements)))
        elif isinstance(array_, String):
            return RTResult().success(Number(len(array_.value)))
        else:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be an array or string",
                exec_ctx
            ))

    execute_len.arg_names = ['array']

    def execute_time(self, exec_ctx):
        return RTResult().success(Number(time.time()))

    execute_time.arg_names = []

    def execute_base64_encode(self, exec_ctx):
        string_ = exec_ctx.symbol_table.get('string')
        if isinstance(string_, String):
            string_converted = str(string_)
            string_bytes = string_converted.encode('ascii')
            base64_bytes = base64.b64encode(string_bytes)
            base64_string = base64_bytes.decode('ascii')
            return RTResult().success(String(base64_string))
        else:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a string",
                exec_ctx
            ))

    execute_base64_encode.arg_names = ['string']

    def execute_base64_decode(self, exec_ctx):
        string_ = exec_ctx.symbol_table.get('string')
        if isinstance(string_, String):
            string_converted = str(string_)

            string_bytes = string_converted.encode('ascii')
            base64_bytes = base64.b64encode(string_bytes)
            base64_string = base64_bytes.decode('ascii')

            string_bytes_decode = base64_string.encode('ascii')
            base64_bytes_decode = base64.b64decode(string_bytes_decode)
            base64_string_decode = base64_bytes_decode.decode('ascii')
            return RTResult().success(String(base64_string_decode))
        else:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a string",
                exec_ctx
            ))

    execute_base64_decode.arg_names = ['string']

    def execute_number_to_unicode(self, exec_ctx):
        number_ = exec_ctx.symbol_table.get('number')
        if isinstance(number_, Number):
            if int(number_) > 1111998:
                return RTResult().failure(RTError(
                    self.pos_start, self.pos_end,
                    "Argument must be a Number less than 1111998",
                    exec_ctx
                ))
            else:
                return RTResult().success(String(chr(int(number_))))
        else:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a Number less than 1111998",
                exec_ctx
            ))

    execute_number_to_unicode.arg_names = ['number']

    def execute_unicode_to_number(self, exec_ctx):
        string_ = exec_ctx.symbol_table.get('string')
        if isinstance(string_, String):
            if len(str(string_)) > 1:
                return RTResult().failure(RTError(
                    self.pos_start, self.pos_end,
                    "Argument must be a 1-Character String",
                    exec_ctx
                ))
            else:
                return RTResult().success(Number(ord(str(string_))))
        else:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a 1-Character String",
                exec_ctx
            ))

    execute_unicode_to_number.arg_names = ['string']

    def execute_format_number(self, exec_ctx):
        number = exec_ctx.symbol_table.get('num')
        if isinstance(number, Number):
            exponent = math.floor(math.log(float(number), 10))
            mantissa = float(number) / (math.pow(10, exponent))
            string_ = f"{mantissa}e{exponent}"
            return RTResult().success(String(string_))
        else:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a Number",
                exec_ctx
            ))

    execute_format_number.arg_names = ['num']

    def execute_run(self, exec_ctx):
        fn = exec_ctx.symbol_table.get('fn')
        if not isinstance(fn, String):
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a string",
                exec_ctx
            ))
        fn = fn.value
        if fn != re.search(".peanut$", fn):
            fn += ".peanut"

        try:
            with open(fn, 'r') as f:
                script = f.read()
        except Exception as e:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                f"Failed to load script \"{fn}\"\n" + str(e),
                exec_ctx
            ))

        _, error = run(fn, script)
        if error:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                f"Failed to finish executing script \"{fn}\"\n" + error.as_string(),
                exec_ctx
            ))
        return RTResult().success(String.no_return)

    execute_run.arg_names = ['fn']

    def execute_use(self, exec_ctx):
        fn = exec_ctx.symbol_table.get('fn')
        if not isinstance(fn, String):
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a string",
                exec_ctx
            ))
        fn = fn.value
        if fn != re.search(".peanut$", fn):
            fn += ".peanut"

        try:
            with open(fn, 'r') as f:
                script = f.read()
        except Exception as e:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                f"Failed to load script \"{fn}\"\n" + str(e),
                exec_ctx
            ))

        _, error = run(fn, script)
        if error:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                f"Failed to finish executing script \"{fn}\"\n" + error.as_string(),
                exec_ctx
            ))
        return RTResult().success(String.no_return)

    execute_use.arg_names = ['fn']

    def execute_read(self, exec_ctx):
        fn = exec_ctx.symbol_table.get('fn')
        if not isinstance(fn, String):
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                "Argument must be a string",
                exec_ctx
            ))
        fn = fn.value
        if fn != re.search(".peanut$", fn):
            fn += ".peanut"

        try:
            with open(fn, 'r') as f:
                script = f.read()
        except Exception as e:
            return RTResult().failure(RTError(
                self.pos_start, self.pos_end,
                f"Failed to load script \"{fn}\"\n" + str(e),
                exec_ctx
            ))

        return RTResult().success(String(script))

    execute_read.arg_names = ['fn']


# endregion


# region BuiltIn Funcs
BuiltInFunction.print = BuiltInFunction("print")
BuiltInFunction.print_return = BuiltInFunction("print_return")
BuiltInFunction.input = BuiltInFunction("input")
BuiltInFunction.input_int = BuiltInFunction("input_int")
BuiltInFunction.clear = BuiltInFunction("clear")
BuiltInFunction.is_number = BuiltInFunction("is_number")
BuiltInFunction.is_string = BuiltInFunction("is_string")
BuiltInFunction.is_array = BuiltInFunction("is_array")
BuiltInFunction.is_function = BuiltInFunction("is_function")
BuiltInFunction.typeof = BuiltInFunction("typeof")
BuiltInFunction.append = BuiltInFunction("append")
BuiltInFunction.remove = BuiltInFunction("remove")
BuiltInFunction.concat = BuiltInFunction("concat")
BuiltInFunction.len = BuiltInFunction("len")
BuiltInFunction.time = BuiltInFunction("time")
BuiltInFunction.base64_encode = BuiltInFunction("base64_encode")
BuiltInFunction.base64_decode = BuiltInFunction("base64_decode")
BuiltInFunction.number_to_unicode = BuiltInFunction("number_to_unicode")
BuiltInFunction.unicode_to_number = BuiltInFunction("unicode_to_number")
BuiltInFunction.format_number = BuiltInFunction("format_number")
BuiltInFunction.run = BuiltInFunction("run")
BuiltInFunction.use = BuiltInFunction("use")
BuiltInFunction.read = BuiltInFunction("read")


# endregion

class Context:
    def __init__(self, display_name, parent=None, parent_entry_pos=None):
        self.display_name = display_name
        self.parent = parent
        self.parent_entry_pos = parent_entry_pos
        self.symbol_table = None


class SymbolTable:
    def __init__(self, parent=None):
        self.symbols = {}
        self.symbols_should_scope = {}
        self.symbols_are_vars = {}
        self.symbols_are_strict_vars = {}
        self.var_types = {}
        self.parent = parent

    def get(self, name):
        value = self.symbols.get(name, None)
        if value is None and self.parent:
            return self.parent.get(name)
        return value

    def getScope(self, name):
        should_scope = self.symbols_should_scope.get(name, None)
        if should_scope is None and self.parent:
            return self.parent.get(name)
        return should_scope

    def isStrict(self, name):
        strict_typed = self.symbols_are_strict_vars.get(name, None)
        if strict_typed is None and self.parent:
            return self.parent.get(name)
        return strict_typed

    def varCheck(self, name):
        is_var = self.symbols_are_vars.get(name, None)
        if is_var is None and self.parent:
            return self.parent.get(name)
        return is_var

    def getType(self, name):
        type_ = self.var_types.get(name, None)
        if type_ is None and self.parent:
            return self.parent.get(name)
        return type_

    def set(self, name, value, is_var=False, is_scoped=False, is_strict=False, type_=None):
        self.symbols[name] = value
        self.symbols_should_scope[name] = is_scoped
        self.symbols_are_vars[name] = is_var
        self.symbols_are_strict_vars[name] = is_strict
        self.var_types[name] = type_

    def remove(self, name):
        del self.symbols[name]


class Interpreter:
    def visit(self, node, context):
        method_name = f'visit_{type(node).__name__}'
        method = getattr(self, method_name, self.no_visit_method)
        return method(node, context)

    def no_visit_method(self, node, context):
        raise Exception(f'No visit_{type(node).__name__} method defined')

    def visit_NumberNode(self, node, context):
        return RTResult().success(
            Number(node.tok.value).set_context(context).set_pos(node.pos_start, node.pos_end)
        )

    def visit_StringNode(self, node, context):
        return RTResult().success(
            String(node.tok.value).set_context(context).set_pos(node.pos_start, node.pos_end)
        )

    def visit_ArrayNode(self, node, context):
        res = RTResult()
        elements = []

        for element_node in node.element_nodes:
            elements.append(res.register(self.visit(element_node, context)))
            if res.should_return(): return res

        return res.success(
            Array(elements).set_context(context).set_pos(node.pos_start, node.pos_end)
        )

    def visit_VarAssignNode(self, node, context):
        res = RTResult()
        var_name = node.var_name_tok.value
        if node.value_node != Number.null:
            value = res.register(self.visit(node.value_node, context))
        else:
            value = Number.null
        if res.should_return(): return res

        global_symbol_table.set(var_name, value, True, False, False)
        return res.success(value)

    def visit_ScopedAssignNode(self, node, context):
        res = RTResult()
        var_name = node.var_name_tok.value
        if node.value_node != Number.null:
            value = res.register(self.visit(node.value_node, context))
        else:
            value = Number.null
        if res.should_return(): return res

        if context.parent is None:
            locked_symbol_table.set(var_name, value, True, True, False)
            print('WARNING: Scoped is redundant in the Global Context!')
        else:
            context.symbol_table.set(var_name, value, True, True, False)
        return res.success(value)

    def visit_StrictAssignNode(self, node, context):
        res = RTResult()
        var_name = node.var_name_tok.value
        type_ = node.var_type
        value = res.register(self.visit(node.value_node, context))
        if res.should_return(): return res

        global_symbol_table.set(var_name, value, True, False, True, type_)
        return res.success(value)

    def visit_AccessNode(self, node, context):
        res = RTResult()
        var_name = node.var_name_tok.value
        value = context.symbol_table.get(var_name)
        should_scope = context.symbol_table.getScope(var_name)

        if context.parent is None:
            value = locked_symbol_table.get(var_name)

        if not value:
            if should_scope is False:
                value = global_symbol_table.get(var_name)
            else:
                return res.failure(RTError(
                    node.pos_start, node.pos_end,
                    f"'{var_name}' is not defined or not in this scope.",
                    context
                ))

        value = value.copy().set_pos(node.pos_start, node.pos_end).set_context(context)
        return res.success(value)

    def visit_BinaryOpNode(self, node, context):
        res = RTResult()
        left = res.register(self.visit(node.left_node, context))
        if res.should_return(): return res
        right = res.register(self.visit(node.right_node, context))
        if res.should_return(): return res

        if node.op_tok.type == TT_PLUS:
            result, error = left.added_to(right)
        elif node.op_tok.type == TT_MINUS:
            result, error = left.subtracted_by(right)
        elif node.op_tok.type == TT_MUL:
            result, error = left.multiplied_by(right)
        elif node.op_tok.type == TT_DIV:
            result, error = left.divided_by(right)
        elif node.op_tok.type == TT_POW:
            result, error = left.pow(right)
        elif node.op_tok.type == TT_MOD:
            result, error = left.modded_by(right)
        elif node.op_tok.type == TT_EE:
            result, error = left.get_comparison_eq(right)
        elif node.op_tok.type == TT_NE:
            result, error = left.get_comparison_ne(right)
        elif node.op_tok.type == TT_LT:
            result, error = left.get_comparison_lt(right)
        elif node.op_tok.type == TT_GT:
            result, error = left.get_comparison_gt(right)
        elif node.op_tok.type == TT_LTE:
            result, error = left.get_comparison_lte(right)
        elif node.op_tok.type == TT_GTE:
            result, error = left.get_comparison_gte(right)
        elif node.op_tok.matches(TT_KEYWORD, 'and'):
            result, error = left.anded_by(right)
        elif node.op_tok.matches(TT_KEYWORD, 'or'):
            result, error = left.ored_by(right)
        if error:
            return res.failure(error)
        else:
            return res.success(result.set_pos(node.pos_start, node.pos_end))

    def visit_UnaryOpNode(self, node, context):
        res = RTResult()
        number = res.register(self.visit(node.node, context))
        if res.should_return(): return res

        error = None

        if node.op_tok.type == TT_MINUS:
            number, error = number.multiplied_by(Number(-1))
        elif node.op_tok.matches(TT_KEYWORD, 'not'):
            number, error = number.notted()

        if error:
            return res.failure(error)
        else:
            return res.success(number.set_pos(node.pos_start, node.pos_end))

    def visit_IfNode(self, node, context):
        res = RTResult()

        for condition, expression, should_return_null in node.cases:
            condition_value = res.register(self.visit(condition, context))
            if res.should_return(): return res

            if condition_value.is_true():
                expr_value = res.register(self.visit(expression, context))
                if res.should_return(): return res
                return res.success(String.no_return if should_return_null else expr_value)

        if node.else_case:
            expression, should_return_null = node.else_case
            else_value = res.register(self.visit(expression, context))
            if res.should_return(): return res
            return res.success(String.no_return if should_return_null else else_value)

        return res.success(String.no_return)

    def visit_ForNode(self, node, context):
        res = RTResult()
        elements = []

        start_value = res.register(self.visit(node.start_value_node, context))
        if res.should_return(): return res

        end_value = res.register(self.visit(node.end_value_node, context))
        if res.should_return(): return res

        if node.step_value_node:
            step_value = res.register(self.visit(node.step_value_node, context))
            if res.should_return(): return res
        else:
            step_value = Number(1)

        i = start_value.value

        if step_value.value >= 0:
            condition = lambda: i < end_value.value
        else:
            condition = lambda: i > end_value.value

        while condition():
            context.symbol_table.set(node.var_name_tok.value, Number(i))
            i += step_value.value

            value = res.register(self.visit(node.body_node, context))
            if res.should_return() and res.loop_should_continue == False and res.loop_should_break == False: return res

            if res.loop_should_continue:
                continue
            if res.loop_should_break:
                break

            elements.append(value)

        return res.success(
            String.no_return if node.should_return_null else
            Array(elements).set_context(context).set_pos(node.pos_start, node.pos_end)
        )

    def visit_WhileNode(self, node, context):
        res = RTResult()
        elements = []

        while True:
            condition = res.register(self.visit(node.condition_node, context))
            if res.should_return(): return res

            if not condition.is_true(): break

            value = res.register(self.visit(node.body_node, context))

            if res.should_return() and res.loop_should_continue is False and res.loop_should_break is False: return res

            if res.loop_should_continue:
                continue
            if res.loop_should_break:
                break

            elements.append(value)

        return res.success(
            String.no_return if node.should_return_null else
            Array(elements).set_context(context).set_pos(node.pos_start, node.pos_end)
        )

    def visit_FuncDefNode(self, node, context):
        res = RTResult()

        func_name = node.var_name_tok.value if node.var_name_tok else None
        body_node = node.body_node
        arg_names = [arg_name.value for arg_name in node.arg_name_toks]
        arg_defaults = [arg_default for arg_default in node.arg_defaults]
        func_value = Function(func_name, body_node, arg_names, arg_defaults, node.should_auto_return).set_context(
            context).set_pos(
            node.pos_start, node.pos_end)

        if node.var_name_tok:
            context.symbol_table.set(func_name, func_value)

        return res.success(func_value)

    def visit_CallNode(self, node, context):
        res = RTResult()
        args = []

        value_to_call = res.register(self.visit(node.node_to_call, context))
        if res.should_return(): return res
        value_to_call = value_to_call.copy().set_pos(node.pos_start, node.pos_end)

        for arg_node in node.arg_nodes:
            args.append(res.register(self.visit(arg_node, context)))
            if res.should_return(): return res

        return_value = res.register(value_to_call.execute(args))
        if res.should_return(): return res
        return_value = return_value.copy().set_pos(node.pos_start, node.pos_end).set_context(context)
        return res.success(return_value)

    def visit_ReturnNode(self, node, context):
        res = RTResult()

        if node.node_to_return:
            value = res.register(self.visit(node.node_to_return, context))
            if res.should_return(): return res
        else:
            value = String.no_return

        return res.success_return(value)

    def visit_ContinueNode(self, node, context):
        return RTResult().success_continue()

    def visit_BreakNode(self, node, context):
        return RTResult().success_break()


# region BuiltIns
locked_symbol_table = SymbolTable()
global_symbol_table = SymbolTable()
global_symbol_table.set("NO_RETURN", String.no_return)
global_symbol_table.set("ZERO", Number.null)
global_symbol_table.set("FALSE_VALUE", Number.false)
global_symbol_table.set("TRUE_VALUE", Number.true)
global_symbol_table.set("false", Number.false)
global_symbol_table.set("true", Number.true)
global_symbol_table.set("INFINITY", Number.infinity)
global_symbol_table.set("NEGATIVE_INF", Number.negative_infinity)
# region Functions
global_symbol_table.set("print", BuiltInFunction.print)
global_symbol_table.set("printReturn", BuiltInFunction.print_return)
global_symbol_table.set("input", BuiltInFunction.input)
global_symbol_table.set("inputNumber", BuiltInFunction.input_int)
global_symbol_table.set("cls", BuiltInFunction.clear)
global_symbol_table.set("isNumber", BuiltInFunction.is_number)
global_symbol_table.set("isString", BuiltInFunction.is_string)
global_symbol_table.set("isArray", BuiltInFunction.is_array)
global_symbol_table.set("isFunction", BuiltInFunction.is_function)
global_symbol_table.set("typeof", BuiltInFunction.typeof)
global_symbol_table.set("append", BuiltInFunction.append)
global_symbol_table.set("removeIndex", BuiltInFunction.remove)
global_symbol_table.set("concat", BuiltInFunction.concat)
global_symbol_table.set("length", BuiltInFunction.len)
global_symbol_table.set("time", BuiltInFunction.time)
global_symbol_table.set("b64Encode", BuiltInFunction.base64_encode)
global_symbol_table.set("b64Decode", BuiltInFunction.base64_decode)
global_symbol_table.set("toUnicode", BuiltInFunction.number_to_unicode)
global_symbol_table.set("fromUnicode", BuiltInFunction.unicode_to_number)
global_symbol_table.set("formatNumber", BuiltInFunction.format_number)
global_symbol_table.set("run", BuiltInFunction.run)
global_symbol_table.set("use", BuiltInFunction.use)
global_symbol_table.set("read", BuiltInFunction.read)


# endregion
# endregion


def run(fn, text):
    lexer = Lexer(fn, text)
    tokens, error = lexer.make_tokens()
    if error: return None, error

    parser = Parser(tokens)
    ast = parser.parse()
    if ast.error: return None, ast.error

    interpreter = Interpreter()
    context = Context('BASE_LEVEL_SCRIPT')
    context.symbol_table = global_symbol_table
    result = interpreter.visit(ast.node, context)

    FILE_NAME = fn
    return result.value, result.error


def run_interpolation(fn, text):
    lexer = Lexer(fn, text)
    tokens, error = lexer.make_tokens()
    if error: return None, error

    parser = Parser(tokens)
    ast = parser.parse()
    if ast.error: return None, ast.error

    interpreter = Interpreter()
    context = Context('BASE_LEVEL_SCRIPT')
    context.symbol_table = global_symbol_table
    result = interpreter.visit(ast.node, context)

    return result.value
