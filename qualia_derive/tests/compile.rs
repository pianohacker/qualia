use trybuild;

#[test]
fn invalid_derive_should_fail() {
    trybuild::TestCases::new().compile_fail("tests/compile-fail/*.rs");
}
