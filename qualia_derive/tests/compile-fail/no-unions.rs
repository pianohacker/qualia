extern crate qualia_derive;
use qualia_derive::ObjectShape;

#[derive(ObjectShape)]
union Foo {
    a: i64,
}

fn main() {}
