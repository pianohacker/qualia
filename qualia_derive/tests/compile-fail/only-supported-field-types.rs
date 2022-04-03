extern crate qualia_derive;
use qualia_derive::ObjectShape;

#[derive(ObjectShape)]
struct Foo {
    a: i64,
    b: f64,
    c: String,
}

#[derive(ObjectShape)]
struct Foo2<'a> {
    a: i64,
    b: &'a str,
    c: String,
}

#[derive(ObjectShape)]
struct Foo3 {
    object_id: i64,
    a: String,
}

fn main() {}
