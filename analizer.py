# -*- coding: utf-8 -*-
"""
Tokenizer para BRIK-Creativo v6
Sintaxis soportada:
  - Asignación: :=
  - Bloques: ¿ ... ?
  - Listas:  ¡ ... !
  - Separador: ,
  - Strings: "..."
  - Números: enteros y reales simples (123, 3.14)
  - Comentarios: a partir de '#' hasta fin de línea

Salida: lista de tuplas (TYPE, value, line, col)
"""

from typing import List, Tuple, Optional

Token = Tuple[str, Optional[object], int, int]  # (TYPE, value, line, col)

class BrikTokenizer:
    def __init__(self, source: str):
        self.src = source
        self.n = len(source)
        self.i = 0
        self.line = 1
        self.col = 1
        # Map de operadores/puntuación a tipos
        self.simple_ops = {
            '¿': 'LBRACE',
            '?': 'RBRACE',
            '¡': 'LBRACKET',
            '!': 'RBRACKET',
            ',': 'COMMA',
        }

    # -------------- utilidades básicas --------------
    def _peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.src[j] if 0 <= j < self.n else ''

    def _advance(self, k: int = 1) -> None:
        for _ in range(k):
            if self.i >= self.n:
                return
            ch = self.src[self.i]
            self.i += 1
            if ch == '\n':
                self.line += 1
                self.col = 1
            else:
                self.col += 1

    def _make(self, typ: str, val: Optional[object], line: int, col: int) -> Token:
        return (typ, val, line, col)

    # -------------- consumidores --------------
    def _skip_ws_and_comments(self) -> None:
        while self.i < self.n:
            ch = self._peek()
            # espacios y saltos de línea
            if ch in (' ', '\t', '\r', '\n'):
                self._advance()
                continue
            # comentario: # hasta fin de línea
            if ch == '#':
                while self.i < self.n and self._peek() != '\n':
                    self._advance()
                continue
            break

    def _read_ident(self) -> Token:
        start_line, start_col = self.line, self.col
        s = []
        ch = self._peek()
        if not (ch.isalpha() or ch.isdigit() or ch == '_'):
            raise SyntaxError(f"[{self.line}:{self.col}] Identificador inválido")
        while True:
            ch = self._peek()
            if ch.isalnum() or ch == '_':
                s.append(ch)
                self._advance()
            else:
                break
        return self._make('IDENT', ''.join(s), start_line, start_col)

    def _read_number(self) -> Token:
        start_line, start_col = self.line, self.col
        s = []
        has_dot = False
        # dígitos iniciales
        while True:
            ch = self._peek()
            if ch.isdigit():
                s.append(ch)
                self._advance()
            elif ch == '.' and not has_dot and self._peek(1).isdigit():
                has_dot = True
                s.append(ch)
                self._advance()
            else:
                break
        txt = ''.join(s)
        if has_dot:
            val = float(txt)
        else:
            val = int(txt)
        return self._make('NUMBER', val, start_line, start_col)

    def _read_string(self) -> Token:
        start_line, start_col = self.line, self.col
        assert self._peek() == '"'
        self._advance()  # consume opening "
        chars = []
        while True:
            if self.i >= self.n:
                raise SyntaxError(f"[{start_line}:{start_col}] String sin cerrar")
            ch = self._peek()
            if ch == '"':
                self._advance()  # closing "
                break
            if ch == '\\':  # escapes simples
                self._advance()
                esc = self._peek()
                if esc == 'n':
                    chars.append('\n')
                elif esc == 't':
                    chars.append('\t')
                elif esc == '"':
                    chars.append('"')
                elif esc == '\\':
                    chars.append('\\')
                else:
                    # escape desconocido: se conserva el carácter escapado
                    chars.append(esc)
                self._advance()
            else:
                chars.append(ch)
                self._advance()
        return self._make('STRING', ''.join(chars), start_line, start_col)

    # -------------- tokenización principal --------------
    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while self.i < self.n:
            self._skip_ws_and_comments()
            if self.i >= self.n:
                break

            ch = self._peek()

            # asignación ':='
            if ch == ':' and self._peek(1) == '=':
                line, col = self.line, self.col
                self._advance(2)
                tokens.append(self._make('ASSIGN', ':=', line, col))
                continue

            # operadores/puntuación simples
            if ch in self.simple_ops:
                typ = self.simple_ops[ch]
                line, col = self.line, self.col
                self._advance()
                tokens.append(self._make(typ, ch, line, col))
                continue

            # string
            if ch == '"':
                tokens.append(self._read_string())
                continue

            # número (empieza por dígito)
            if ch.isdigit():
                tokens.append(self._read_number())
                continue

            # identificador
            if ch.isalpha() or ch == '_':
                tokens.append(self._read_ident())
                continue

            # cualquier otro carácter es error (incluye '.'
            # fuera de número, ';', etc.)
            raise SyntaxError(f"[{self.line}:{self.col}] Carácter inesperado: {repr(ch)}")

        tokens.append(self._make('EOF', None, self.line, self.col))
        return tokens
