var UglifyJS = require("uglify-js");

var define_adjuster = new UglifyJS.TreeWalker(function(node, descend) {
    if (node instanceof UglifyJS.AST_Call && node.expression.thedef && node.expression.name == 'define' && node.expression.thedef.global) {
        if (this.encountered_define) {
            throw new Error('Found more than one call to define() in ' + this.name);
        }
        this.encountered_define = true;
        if (node.args.length == 1 || (node.args.length == 2 && node.args[0].start.type != 'string')) {
            if (conf.minify) {
                node.args.splice(0, 0, new UglifyJS.AST_String({ value: this.name, quote: "'", raw: "'" + this.name + "'" }));
            } else {
                this.start = node.args[0].start.pos;
                this.end = null;
            }
        } else if (this.replaceExisting) {
            if (conf.minify) {
                node.args[0].value = this.name;
                node.args[0].quote = "'";
                node.args[0].raw = "'" + this.name + "'";
            } else {
                this.start = node.args[0].start.pos;
                this.end = node.args[0].end.endpos;
            }
        }
        descend();
        // TODO: either early abort via exception,
        // or check for duplicate define() call
        return true;
    }
});

define_adjuster.reset = function(name, replaceExisting) {
    this.encountered_define = false;
    this.start = null;
    this.end = null;
    this.name = name;
    this.replaceExisting = replaceExisting;
};

var conf = %s;

if (conf.minify) {

    var toplevel = null;
    for (var i = 0; i < conf.files.length; i++) {
        var ast = UglifyJS.parse(conf.contents[i], {'filename': conf.files[i]});
        define_adjuster.reset(conf.names[i], conf.replaceExisting[i]);
        ast.figure_out_scope();
        ast.walk(define_adjuster);
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
    toplevel = compressed_ast;
    console.log(toplevel.print_to_string());

} else {

    for (var i = 0; i < conf.files.length; i++) {
        console.log('\n//' + Array(conf.files[i].length + 5).join("-") + '//');
        console.log('//  ' + conf.files[i] + '  //');
        console.log('//' + Array(conf.files[i].length + 5).join("-") + '//\n');
        var ast = UglifyJS.parse(conf.contents[i], {'filename': conf.files[i]});
        ast.figure_out_scope();
        define_adjuster.reset(conf.names[i], conf.replaceExisting[i]);
        ast.walk(define_adjuster);
        if (define_adjuster.start === null) {
            console.log(conf.contents[i]);
        } else if (define_adjuster.end === null) {
            console.log(conf.contents[i].slice(0, define_adjuster.start) +
                    "'" + conf.names[i] + "', " +
                    conf.contents[i].slice(define_adjuster.start));
        } else {
            console.log(conf.contents[i].slice(0, define_adjuster.start) +
                    "'" + conf.names[i] + "'" +
                    conf.contents[i].slice(define_adjuster.end));
        }
    }

}

