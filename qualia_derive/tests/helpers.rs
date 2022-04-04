use qualia::{object, ConversionError, ObjectShape, ObjectShapeWithId, Result, Q};

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

#[test]
fn can_get_and_set_id() -> Result<(), ConversionError> {
    #[derive(ObjectShape)]
    struct IdShape {
        object_id: Option<i64>,
    }

    assert_eq!(
        IdShape {
            object_id: Some(49)
        }
        .get_object_id(),
        Some(49)
    );

    Ok(())
}
