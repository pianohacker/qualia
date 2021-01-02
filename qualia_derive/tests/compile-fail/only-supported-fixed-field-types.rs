extern crate qualia_derive;
use qualia_derive::ObjectShape;

#[object_fixed_fields("foo" => 4.5)]
#[derive(ObjectShape)]
struct FixedFoo {
    a: i64,
    c: String,
}

fn main() {}
