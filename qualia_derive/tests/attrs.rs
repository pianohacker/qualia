use predicates::prelude::*;
use qualia::{object, ConversionError, Object, Result};
use qualia_derive::ObjectShape;
use std::convert::TryFrom;

macro_rules! assert_is_err_matching {
    ($result:expr, $pattern:expr$(,)?) => {
        let predicate = predicate::str::is_match($pattern).expect("error pattern invalid");
        let error = &($result).err().expect("unexpected success").to_string();

        if let Some(case) = predicate.find_case(false, error) {
            panic!("Unexpected error, failed {:?}\n{:?}", case, error);
        }
    };
}

#[test]
fn can_convert_with_custom_field_names() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    struct CustomShape {
        #[field("my-name")]
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

#[test]
fn can_convert_with_fixed_fields() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    #[fixed_fields("foo" => 1, "type" => "shape")]
    struct ShapeWithType {
        width: i64,
        height: i64,
    }

    let shape: Object = ShapeWithType {
        width: 8,
        height: 11,
    }
    .into();

    assert_eq!(
        shape,
        object!(
            "type" => "shape",
            "foo" => 1,
            "width" => 8,
            "height" => 11,
        ),
    );

    let obj: Object = object!(
        "type" => "shape",
        "foo" => 1,
        "width" => 8,
        "height" => 11,
    );

    assert_eq!(
        ShapeWithType::try_from(obj)?,
        ShapeWithType {
            width: 8,
            height: 11,
        }
    );

    Ok(())
}

#[test]
fn can_convert_with_rest_fields() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    struct ShapeWithRest {
        width: i64,
        height: i64,
        #[rest_fields]
        rest: Object,
    }

    let shape: Object = ShapeWithRest {
        width: 8,
        height: 11,
        rest: object!(),
    }
    .into();

    assert_eq!(
        shape,
        object!(
            "width" => 8,
            "height" => 11,
        ),
    );

    let shape2: Object = ShapeWithRest {
        width: 8,
        height: 11,
        rest: object!("extra" => 1, "extra2" => 3),
    }
    .into();

    assert_eq!(
        shape2,
        object!(
            "width" => 8,
            "height" => 11,
            "extra" => 1,
            "extra2" => 3,
        ),
    );

    let obj: Object = object!(
        "width" => 8,
        "height" => 11,
        "foo" => "bar",
    );

    assert_eq!(
        ShapeWithRest::try_from(obj)?,
        ShapeWithRest {
            width: 8,
            height: 11,
            rest: object!("foo" => "bar"),
        }
    );

    Ok(())
}

#[test]
fn converting_with_fixed_fields_fails_when_invalid() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    #[fixed_fields("foo" => 1, "type" => "shape")]
    struct ShapeWithTypeInvalid {
        width: i64,
        height: i64,
    }

    assert_is_err_matching!(
        ShapeWithTypeInvalid::try_from(object!(
            "type" => "shape",
            "width" => 8,
            "height" => 11,
        )),
        "foo.*missing",
    );

    assert_is_err_matching!(
        ShapeWithTypeInvalid::try_from(object!(
            "type" => "shape",
            "foo" => "blah"
            "width" => 8,
            "height" => 11,
        )),
        "foo.*number",
    );

    assert_is_err_matching!(
        ShapeWithTypeInvalid::try_from(object!(
            "type" => "shape",
            "foo" => 2,
            "width" => 8,
            "height" => 11,
        )),
        "fixed.*foo.*1.*2",
    );

    Ok(())
}

#[test]
fn can_get_related() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    struct ShapeGroup {
        #[field("my-name")]
        name: String,
        width: i64,
        height: i64,
    }

    #[derive(Debug, ObjectShape, PartialEq)]
    struct CustomShape {
        #[field("my-name")]
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
