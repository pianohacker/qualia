extern crate qualia_derive;
use qualia_derive::ObjectShape;

#[derive(ObjectShape)]
struct Foo {}

#[derive(ObjectShape)]
struct Foo2 {
    #[related(Foo)]
    foo_id: i64,
}

fn main() {}
