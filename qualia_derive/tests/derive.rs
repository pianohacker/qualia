use predicates::prelude::*;
use qualia::{object, ConversionError, Object, Result};
use qualia_derive::ObjectShape;
use std::convert::TryFrom;

#[derive(Debug, ObjectShape, PartialEq)]
struct Shape {
    name: String,
    width: i64,
    height: i64,
}

#[derive(Debug, ObjectShape, PartialEq)]
struct ShapeWithId {
    object_id: Option<i64>,
    name: String,
    width: i64,
}

fn result_is_err_matching<T, E: std::error::Error>(r: Result<T, E>, pattern: &str) -> bool {
    predicate::str::is_match(pattern)
        .unwrap()
        .eval(&r.err().unwrap().to_string())
}

#[test]
fn can_convert_from_object() -> Result<(), ConversionError> {
    assert_eq!(
        Shape::try_from(object!("name" => "letter", "width" => 8, "height" => 11))?,
        Shape {
            name: "letter".to_string(),
            width: 8,
            height: 11
        }
    );

    assert_eq!(
        Shape::try_from(&object!("name" => "letter", "width" => 8, "height" => 11))?,
        Shape {
            name: "letter".to_string(),
            width: 8,
            height: 11
        }
    );

    Ok(())
}

#[test]
fn can_convert_from_object_with_id() -> Result<(), ConversionError> {
    assert_eq!(
        ShapeWithId::try_from(object!("object_id" => 49, "name" => "letter", "width" => 8))?,
        ShapeWithId {
            object_id: Some(49),
            name: "letter".to_string(),
            width: 8,
        }
    );

    assert_eq!(
        ShapeWithId::try_from(object!("name" => "letter", "width" => 8))?,
        ShapeWithId {
            object_id: None,
            name: "letter".to_string(),
            width: 8,
        }
    );

    Ok(())
}

#[test]
fn converting_fails_when_fields_missing() -> Result<(), ConversionError> {
    assert!(result_is_err_matching(
        Shape::try_from(object!("name" => "letter", "height" => 11)),
        "width.*missing",
    ));

    Ok(())
}

#[test]
fn converting_fails_when_fields_wrong_type() -> Result<(), ConversionError> {
    assert!(result_is_err_matching(
        Shape::try_from(object!("name" => 4, "width" => 8, "height" => 11)),
        "name.*string",
    ));

    assert!(result_is_err_matching(
        Shape::try_from(object!("name" => "letter", "width" => "potato", "height" => 11)),
        "width.*number",
    ));

    assert!(result_is_err_matching(
        ShapeWithId::try_from(
            object!("object_id" => "string", "name" => "letter", "width" => "potato")
        ),
        "object_id.*number",
    ));

    Ok(())
}

#[test]
fn can_convert_to_object() -> Result<(), ConversionError> {
    let obj: Object = Shape {
        name: "letter".to_string(),
        width: 8,
        height: 11,
    }
    .into();

    assert_eq!(
        obj,
        object!("name" => "letter", "width" => 8, "height" => 11),
    );

    Ok(())
}

#[test]
fn can_convert_to_object_with_id() -> Result<(), ConversionError> {
    let obj: Object = ShapeWithId {
        object_id: Some(64),
        name: "letter".to_string(),
        width: 8,
    }
    .into();

    assert_eq!(
        obj,
        object!("object_id" => 64, "name" => "letter", "width" => 8),
    );

    let obj2: Object = ShapeWithId {
        object_id: None,
        name: "letter".to_string(),
        width: 8,
    }
    .into();

    assert_eq!(obj2, object!("name" => "letter", "width" => 8),);

    Ok(())
}
