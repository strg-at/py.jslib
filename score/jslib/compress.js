var UglifyJS = require("uglify-js");

var define_adjuster = new UglifyJS.TreeWalker(function(node, descend) {
    if (node instanceof UglifyJS.AST_Call && node.expression.thedef && node.expression.name == 'define' && node.expression.thedef.global) {
        if (node.args.length == 1 || (node.args.length == 2 && node.args[0].start.type != 'string')) {
            node.args.splice(0, 0, new UglifyJS.AST_String({ value: this.name, quote: "'", raw: "'" + this.name + "'" }));
        } else {
            node.args[0].value = this.name;
            node.args[0].quote = "'";
            node.args[0].raw = "'" + this.name + "'";
        }
        descend();
        // TODO: either early abort via exception,
        // or check for duplicate define() call
        return true;
    }
});

var conf = %s;

var numfiles = conf.files.length;
var toplevel = null;
for (var i = 0; i < numfiles; i++) {
    var ast = UglifyJS.parse(conf.contents[i], {'filename': conf.files[i]});
    define_adjuster.name = conf.names[i];
    // ast.figure_out_scope();
    // ast.walk(define_adjuster);
    if (!toplevel) {
        toplevel = ast;
    } else {
        toplevel.body = toplevel.body.concat(ast.body);
        toplevel.end = ast.end;
    }
}
toplevel.figure_out_scope();
var compressor = UglifyJS.Compressor();
var compressed_ast = toplevel.transform(compressor);
compressed_ast.figure_out_scope();
compressed_ast.compute_char_frequency();
compressed_ast.mangle_names();
console.log(compressed_ast.print_to_string());
