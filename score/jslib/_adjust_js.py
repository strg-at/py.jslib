import slimit.parser
import slimit.ast
from slimit.visitors.nodevisitor import ASTVisitor


class Parser(slimit.parser.Parser):

    def p_identifier(self, p):
        """identifier : ID"""
        slimit.parser.Parser.p_identifier(self, p)
        p[0].lexpos = p.slice[1].lexpos


class DefineAdjuster(ASTVisitor):

    def __init__(self, name, content):
        self.name = name
        self.content = content
        self.start = None
        self.replace = None

    def replace_content(self):
        parser = Parser()
        open('/tmp/test.js', 'w').write(self.content)
        tree = parser.parse(self.content)
        self.visit(tree)
        if self.start is None:
            raise Exception('Could not find call to define()')
        lexer = slimit.lexer.Lexer()
        lexer.input(self.content)
        for token in lexer:
            if token.lexpos <= self.start:
                continue
            if not self.replace:
                if token.value != '(':
                    continue
                return self.content[:token.lexpos + 1] + \
                    ('"%s",' % self.name) + \
                    self.content[token.lexpos + 1:]
            if token.type == 'STRING' or token.type == 'ID':
                return self.content[:token.lexpos] + \
                    ('"%s",' % self.name) + \
                    self.content[token.lexpos + len(token.value) + 1:]
        return self.content

    def visit_FunctionCall(self, node):
        if getattr(node.identifier, 'value', None) == 'define':
            self.start = node.identifier.lexpos
            if len(node.args) == 3:
                self.replace = node.args[0]
        self.generic_visit(node)
