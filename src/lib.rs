//! A document store with a flexible query language and built-in undo support.

pub mod object;
pub mod query;
pub mod query_builder;
pub mod store;

#[doc(inline)]
pub use object::*;
#[doc(inline)]
pub use qualia_derive::ObjectShape;
#[doc(inline)]
pub use query_builder::Q;
#[doc(inline)]
pub use store::*;
