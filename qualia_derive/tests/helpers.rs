use qualia::{object, ConversionError, ObjectShape, Result, Q};

#[test]
fn returns_query_helper() -> Result<(), ConversionError> {
    #[derive(ObjectShape)]
    #[fixed_fields("a" => 1, "b" => "c")]
    struct QueriedShape {
        width: i64,
    }

    assert_eq!(
        QueriedShape::q().build(),
        Q.equal("a", 1).equal("b", "c").build()
    );

    Ok(())
}
