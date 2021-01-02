use predicates::prelude::*;
use qualia::{object, ConversionError, Object, Result};
use qualia_derive::ObjectShape;
use std::convert::TryFrom;
// use tempfile::{Builder, TempDir};

// fn open_store<'a>(tempdir: &TempDir, name: &str) -> Store {
//     Store::open(tempdir.path().join(name)).unwrap()
// }

// fn test_dir() -> TempDir {
//     Builder::new().prefix("qualia-store").tempdir().unwrap()
// }

// fn populated_store() -> Result<(Store, TempDir)> {
//     let test_dir = test_dir();
//     let mut store = open_store(&test_dir, "store.qualia");

//     let checkpoint = store.checkpoint()?;
//     checkpoint.add(object!("name" => "one", "blah" => "blah"))?;
//     checkpoint.add(object!("name" => "two", "blah" => "halb"))?;
//     checkpoint.add(object!("name" => "three", "blah" => "BLAH"))?;
//     checkpoint.add(object!("name" => "four", "blah" => "blahblah"))?;
//     checkpoint.commit("populate store")?;

//     Ok((store, test_dir))
// }
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

#[test]
fn can_convert_with_custom_field_names() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    struct CustomShape {
        #[object_field("my-name")]
        name: String,
        width: i64,
        height: i64,
    }

    let shape: Object = CustomShape {
        name: "letter".to_string(),
        width: 8,
        height: 11,
    }
    .into();

    assert_eq!(
        shape,
        object!("my-name" => "letter", "width" => 8, "height" => 11),
    );

    let obj: Object = object!(
        "my-name" => "letter",
        "width" => 8,
        "height" => 11,
    );

    assert_eq!(
        CustomShape::try_from(obj)?,
        CustomShape {
            name: "letter".to_string(),
            width: 8,
            height: 11,
        }
    );

    Ok(())
}