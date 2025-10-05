from dataclasses import dataclass
from typing import List, Optional, Any
import json
import re
import os

@dataclass
class Token:
    type: str
    value: object
    line: int
    col: int

class BrikTokenizer:
    """
    Tokenizador mínimo para BRIK (sólo lo necesario para tetris.brik y snake.brik):
      - Comentarios: '# ...' (ignorados)
      - Strings: "..." con escapes estándar (\n, \t, \", \\)
      - Números: enteros y flotantes (incluye .5 y 42.)
      - Asignación: ':='
      - Diccionarios: '¿' ... '?'
      - Listas: '¡' ... '!'
      - Separador: ','
      - Identificadores: [A-Za-z_][A-Za-z0-9_]*
      - Espacios/blancos y saltos de línea ignorados (sólo para line/col)
    """
    _SPEC = [
        ("COMMENT",      r"\#.*"),
        ("STRING",       r"\"(?:\\.|[^\"\\])*\""),
        ("NUMBER",       r"-?(?:\d+\.\d*|\.\d+|\d+)"),
        ("ASSIGN_COLON", r":="),
        ("LDICT",        r"¿"),
        ("RDICT",        r"\?"),
        ("LLIST",        r"¡"),
        ("RLIST",        r"!"),
        ("COMMA",        r","),
        ("IDENT",        r"[A-Za-z_][A-Za-z0-9_]*"),
        ("NEWLINE",      r"\n"),
        ("SKIP",         r"[ \t\r]+"),
        ("MISMATCH",     r"."),   # cualquier otro carácter
    ]
    _MASTER = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in _SPEC))

    def __init__(self, source: str):
        self.source = source

    def tokenize(self):
        tokens = []
        line = 1
        line_start = 0

        for mo in self._MASTER.finditer(self.source):
            kind = mo.lastgroup
            text = mo.group()

            if kind == "NEWLINE":
                line += 1
                line_start = mo.end()
                continue
            if kind in ("SKIP", "COMMENT"):
                continue

            col = mo.start() - line_start + 1

            if kind == "STRING":
                value = bytes(text[1:-1], "utf-8").decode("unicode_escape")
            elif kind == "NUMBER":
                value = float(text) if "." in text else int(text)
            elif kind == "MISMATCH":
                # Cualquier caracter que no pertenezca al lenguaje es error
                raise SyntaxError(
                    f"[{line}:{col}] Carácter inesperado: {repr(text)}.\n"
                    f"Sugerencia: verifica la sintaxis BRIK (listas ¡ !, diccionarios ¿ ?, asignación :=, "
                    f"strings entre comillas)."
                )
            else:
                value = text

            tokens.append(Token(kind, value, line, col))

        return tokens

@dataclass
class ParseError(Exception):
    message: str
    line: int
    col: int
    def __str__(self):
        return f"[{self.line}:{self.col}] {self.message}"

class BrikParser:
    """
    Gramática BRIK compatible con el tokenizador mínimo:

      programa        ::= (asignacion)* EOF
      asignacion      ::= IDENT ':=' expr

      expr            ::= STRING | NUMBER | IDENT | lista | diccionario
      lista           ::= '¡' [ expr (',' expr)* ] '!'
      diccionario     ::= '¿' [ par (',' par)* ] '?'
      par             ::= IDENT ':=' expr

    Notas:
      - Las claves de diccionario son IDENT (no strings).
      - Dentro de diccionarios también se usa ':='.
      - Ident no definido en contexto → {"ref": "ident"} para resolver luego.
    """

    def __init__(self, tokens: List["Token"]):
        self.tokens = tokens
        self.i = 0
        self.symbols = {}

    def _peek(self) -> Optional["Token"]:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _eat(self, expected_types: Optional[List[str]] = None) -> "Token":
        tok = self._peek()
        if tok is None:
            last = self.tokens[self.i-1] if self.i > 0 else None
            line, col = (last.line, last.col) if last else (1, 1)
            raise ParseError("Fin de archivo inesperado", line, col)
        if expected_types and tok.type not in expected_types:
            raise ParseError(
                f"Se esperaba {expected_types}, se encontró {tok.type} (‘{tok.value}’)",
                tok.line, tok.col
            )
        self.i += 1
        return tok

    def _match(self, *types: str) -> Optional["Token"]:
        tok = self._peek()
        if tok and tok.type in types:
            self.i += 1
            return tok
        return None

    # -------------- entrada --------------
    def parse(self) -> dict:
        while self._peek() is not None:
            # Permite comas sueltas entre sentencias si el archivo las trae
            if self._peek().type == "COMMA":
                self.i += 1
                continue
            if self._peek().type == "IDENT":
                self._parse_assignment(self.symbols)
            else:
                t = self._peek()
                raise ParseError(
                    f"Se esperaba un identificador al inicio de sentencia, se encontró {t.type} (‘{t.value}’)",
                    t.line, t.col
                )
        return self.symbols

    def _parse_assignment(self, table: dict):
        key_tok = self._eat(["IDENT"])
        self._eat(["ASSIGN_COLON"])  # ':='
        value = self._parse_expr()
        table[key_tok.value] = value

    # -------------- expresiones --------------
    def _parse_expr(self) -> Any:
        tok = self._peek()
        if tok is None:
            raise ParseError("Se esperaba una expresión", 1, 1)

        if tok.type == "STRING":
            return self._eat().value
        if tok.type == "NUMBER":
            return self._eat().value
        if tok.type == "IDENT":
            name = self._eat().value
            # Resolución temprana si ya existe en el entorno
            if name in self.symbols:
                return self.symbols[name]
            return {"ref": name}
        if tok.type == "LLIST":
            return self._parse_list()
        if tok.type == "LDICT":
            return self._parse_dict()

        raise ParseError(f"Expresión inesperada: {tok.type} (‘{tok.value}’)", tok.line, tok.col)

    # -------------- compuestos --------------
    def _parse_list(self) -> list:
        self._eat(["LLIST"])  # '¡'
        items = []
        # lista vacía
        if self._match("RLIST"):  # '!'
            return items

        while True:
            items.append(self._parse_expr())
            if self._match("COMMA"):
                continue
            self._eat(["RLIST"])  # '!'
            break
        return items

    def _parse_dict(self) -> dict:
        self._eat(["LDICT"])  # '¿'
        data = {}
        # diccionario vacío
        if self._match("RDICT"):  # '?'
            return data

        while True:
            if self._match("COMMA"):
                continue

            key_tok = self._eat(["IDENT"])
            self._eat(["ASSIGN_COLON"])  # ':=' también dentro de ¿ ? 
            value = self._parse_expr()
            data[key_tok.value] = value

            if self._match("COMMA"):
                continue
            nxt = self._peek()
            if nxt is None:
                # faltó cerrar '?'
                raise ParseError("Falta cerrar el diccionario con '?'", key_tok.line, key_tok.col)
            if nxt.type == "RDICT":
                self._eat(["RDICT"])
                break
        return data

def load_file_content(filepath):
    """
    Carga el contenido de un archivo de texto.
    Maneja el error si el archivo no existe.
    """
    if not os.path.exists(filepath):
        print(f"Error: El archivo '{filepath}' no se encontro. Asegurate de que el archivo exista en la misma carpeta que el script.")
        return None
    
    with open(filepath, 'r', encoding='utf-8') as file:
        return file.read()

def save_ast_to_file(ast, filepath):
    """
    Guarda el AST en un archivo de texto en formato JSON.
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as file:
            json.dump(ast, file, indent=4)
        print(f"AST guardado exitosamente en '{filepath}'")
    except Exception as e:
        print(f"Error al guardar el archivo: {e}")

# --- Zona de ejecucion ---
# 1. Especifica la ruta del archivo a procesar
file_path = "snake.brik"
ast_file_path = "arbol.ast"

# 2. Carga el contenido del archivo
source_code = load_file_content(file_path)

if source_code:
    # 3. Analisis Lexico
    print("--- Analisis Lexico (Lexer) ---")
    tokenizer = BrikTokenizer(source_code)
    tokens = tokenizer.tokenize()
    print("Tokens reconocidos:")
    for token in tokens:
        print(token)
    
    # 4. Analisis Sintactico y gestion de Tabla de Simbolos
    print("\n--- Analisis Sintactico (Parser) ---")
    parser = BrikParser(tokens)
    try:
        ast_and_symbol_table = parser.parse()
        print("Sintaxis correcta. Se ha construido el Arbol de Sintaxis Abstracta (AST) / Tabla de Simbolos.")
        print("Contenido del AST:")
        print(json.dumps(ast_and_symbol_table, indent=4))
        
        # 5. Guardar el AST en el archivo
        save_ast_to_file(ast_and_symbol_table, ast_file_path)
        
    except (SyntaxError, NameError) as e:
        print(f"Error en la sintaxis: {e}")
