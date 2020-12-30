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

#[test]
fn can_convert_from_object() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    struct Rectangle {
        width: i64,
        height: i64,
    }

    assert_eq!(
        Rectangle::try_from(object!("width" => 8, "height" => 11))?,
        Rectangle {
            width: 8,
            height: 11
        }
    );

    Ok(())
}

#[test]
fn can_convert_to_object() -> Result<(), ConversionError> {
    #[derive(Debug, ObjectShape, PartialEq)]
    struct Rectangle {
        width: i64,
        height: i64,
    }

    let obj: Object = Rectangle {
        width: 8,
        height: 11,
    }
    .into();

    assert_eq!(obj, object!("width" => 8, "height" => 11),);

    Ok(())
}
