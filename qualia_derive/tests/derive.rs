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
