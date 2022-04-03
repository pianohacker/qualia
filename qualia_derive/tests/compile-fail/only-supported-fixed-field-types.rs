extern crate qualia_derive;
use qualia_derive::ObjectShape;

#[derive(ObjectShape)]
#[fixed_fields("foo" => 4.5)]
struct FixedFoo {
    a: i64,
    c: String,
}

fn main() {}
