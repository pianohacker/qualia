//! Derive macros for easily translating between objects in Qualia and Rust structs.

extern crate proc_macro;
use convert_case::{Case, Casing};
use proc_macro::TokenStream;
use proc_macro2::TokenStream as TokenStream2;
use quote::{format_ident, quote, quote_spanned, ToTokens};
use syn::{parse_macro_input, DeriveInput};

macro_rules! error_stream {
    ( $span:expr, $message:expr ) => {
        quote_spanned!($span=> compile_error!($message);).into()
    }
}

macro_rules! try_or_context {
    ( $expr:expr, $message:expr$(,)? ) => {
        match $expr {
            Ok(x) => x,
            Err(span) => return error_stream!(span, $message),
        }
    };
}

macro_rules! try_or_error {
    ( $expr:expr$(,)? ) => {
        match $expr {
            Ok(x) => x,
            Err(e) => return e.to_compile_error().into(),
        }
    };
}

fn parse_field_name(field: &syn::Field) -> syn::Result<String> {
    if let Some(attr) = field
        .attrs
        .iter()
        .find(|attr| attr.style == syn::AttrStyle::Outer && attr.path.is_ident("field"))
    {
        attr.parse_args::<syn::LitStr>().map(|lit| lit.value())
    } else {
        Ok(field.ident.clone().unwrap().to_string())
    }
}

#[derive(Debug)]
struct ParsedField {
    ident: proc_macro2::Ident,
    name: String,
    accessor: TokenStream2,
    inserter: TokenStream2,
    related_impl: Option<TokenStream2>,
}

fn base_accessor(field_name: &String) -> TokenStream2 {
    quote!(
        get(#field_name)
        .ok_or(qualia::ConversionError::FieldMissing(#field_name.to_string()))?
    )
}

fn number_accessor(field_name: &String) -> TokenStream2 {
    let base_accessor = base_accessor(field_name);

    quote!(
        #base_accessor
        .as_number()
        .ok_or(
            qualia::ConversionError::FieldWrongType(
                #field_name.to_string(),
                "number".to_string(),
            ),
        )?
    )
}

fn string_accessor(field_name: &String) -> TokenStream2 {
    let base_accessor = base_accessor(field_name);

    quote!(
        #base_accessor
        .as_str()
        .ok_or(
            qualia::ConversionError::FieldWrongType(
                #field_name.to_string(),
                "string".to_string(),
            ),
        )?
        .clone()
    )
}

fn object_id_accessor() -> TokenStream2 {
    quote!(get("object_id")
        .map(
            |f| f.as_number().ok_or(qualia::ConversionError::FieldWrongType(
                "object_id".to_string(),
                "number".to_string(),
            ),)
        )
        .transpose()?)
}

#[allow(unused)]
fn option_i64_path() -> syn::TypePath {
    syn::parse_str("Option<i64>").unwrap()
}

fn related_impl(field: &syn::Field) -> syn::Result<Option<TokenStream2>> {
    if let Some(attr) = field
        .attrs
        .iter()
        .find(|attr| attr.style == syn::AttrStyle::Outer && attr.path.is_ident("related"))
    {
        let typ = attr.parse_args::<syn::TypePath>()?;
        let field_ident = field.ident.clone();
        let helper_base = field
            .ident
            .clone()
            .unwrap()
            .to_string()
            .to_case(Case::Snake)
            .replace("_id", "");
        let fetch_name = format_ident!("fetch_{}", helper_base);

        Ok(Some(quote!(
            fn #fetch_name(&self, store: &qualia::Store) -> qualia::Result<#typ> where #typ: qualia::ObjectShapeWithId {
                store.query(<#typ as qualia::ObjectShape>::q().id(self.#field_ident)).one_as()
            }
        )))
    } else {
        Ok(None)
    }
}

fn parse_fields(
    named_fields: &syn::FieldsNamed,
) -> syn::Result<(Vec<ParsedField>, Option<syn::Ident>)> {
    let mut rest_field_ident = None;

    Ok((
        named_fields
            .named
            .iter()
            .map(|field| {
                if let Some(_) = field.attrs.iter().find(|attr| {
                    attr.style == syn::AttrStyle::Outer && attr.path.is_ident("rest_fields")
                }) {
                    rest_field_ident = Some(field.ident.clone().unwrap());
                    return Ok(None);
                }

                let field_type =
                    match &field.ty {
                        syn::Type::Path(p) => p,
                        _ => return Err(syn::Error::new_spanned(
                            &field.ty,
                            "fields in ObjectShape must be simple types (usually i64 or String)",
                        )),
                    };

                let field_name = parse_field_name(&field)?;

                let field_type_accessor = if field_name == "object_id" {
                    if *field_type == option_i64_path() {
                        Ok(object_id_accessor())
                    } else {
                        Err(syn::Error::new_spanned(
                            &field_type.path,
                            "object_id field of OptionShape must be Option<i64>",
                        ))
                    }
                } else if field_type.path.is_ident("i64") {
                    Ok(number_accessor(&field_name))
                } else if field_type.path.is_ident("String") {
                    Ok(string_accessor(&field_name))
                } else {
                    Err(syn::Error::new_spanned(
                        &field_type.path,
                        "fields in ObjectShape must be i64 or String",
                    ))
                }?;

                let field_ident = field.ident.clone().unwrap();
                let field_inserter = if field_name == "object_id" {
                    quote!(
                        if let Some(object_id) = self.#field_ident {
                            result.insert("object_id".into(), object_id.into());
                        }
                    )
                } else {
                    quote!(result.insert(#field_name.into(), self.#field_ident.into());)
                };

                Ok(Some(ParsedField {
                    ident: field_ident,
                    name: field_name,
                    accessor: field_type_accessor,
                    inserter: field_inserter,
                    related_impl: related_impl(&field)?,
                }))
            })
            .collect::<syn::Result<Vec<_>>>()?
            .into_iter()
            .filter_map(|x| x)
            .collect(),
        rest_field_ident,
    ))
}

#[derive(Debug)]
enum FixedFieldValue {
    Number(syn::LitInt),
    String(syn::LitStr),
}

impl syn::parse::Parse for FixedFieldValue {
    fn parse(input: &syn::parse::ParseBuffer<'_>) -> syn::Result<Self> {
        let lookahead = input.lookahead1();
        if lookahead.peek(syn::LitInt) {
            input.parse().map(FixedFieldValue::Number)
        } else if lookahead.peek(syn::LitStr) {
            input.parse().map(FixedFieldValue::String)
        } else {
            Err(lookahead.error())
        }
    }
}

impl quote::ToTokens for FixedFieldValue {
    fn to_tokens(&self, tokens: &mut TokenStream2) {
        match self {
            FixedFieldValue::Number(n) => n.to_tokens(tokens),
            FixedFieldValue::String(s) => s.to_tokens(tokens),
        }
    }
}

#[derive(Debug)]
struct FixedField {
    name: syn::LitStr,
    _arrow_token: syn::token::FatArrow,
    value: FixedFieldValue,
}

impl FixedField {
    fn accessor(&self) -> TokenStream2 {
        match self.value {
            FixedFieldValue::Number(_) => number_accessor(&self.name.value()),
            FixedFieldValue::String(_) => string_accessor(&self.name.value()),
        }
    }
}

impl syn::parse::Parse for FixedField {
    fn parse(input: &syn::parse::ParseBuffer<'_>) -> syn::Result<Self> {
        Ok(FixedField {
            name: input.parse()?,
            _arrow_token: input.parse()?,
            value: input.parse()?,
        })
    }
}

#[derive(Debug)]
struct FixedFields {
    fields: syn::punctuated::Punctuated<FixedField, syn::Token![,]>,
}

impl syn::parse::Parse for FixedFields {
    fn parse(input: &syn::parse::ParseBuffer<'_>) -> syn::Result<Self> {
        Ok(FixedFields {
            fields: input.parse_terminated(FixedField::parse)?,
        })
    }
}

fn parse_fixed_fields(attrs: &Vec<syn::Attribute>) -> syn::Result<Vec<FixedField>> {
    let attr = match attrs
        .iter()
        .find(|attr| attr.style == syn::AttrStyle::Outer && attr.path.is_ident("fixed_fields"))
    {
        Some(a) => a,
        None => return Ok(Vec::new()),
    };

    let fixed_fields: FixedFields = attr.parse_args()?;

    Ok(fixed_fields
        .fields
        .into_pairs()
        .map(|p| match p {
            syn::punctuated::Pair::Punctuated(f, _) => f,
            syn::punctuated::Pair::End(f) => f,
        })
        .collect())
}

/// Automatically translate between properties of Qualia objects and fields of structs.
///
/// # Basic example
///
/// ```
/// # use qualia::{object, Object};
/// # use qualia_derive::ObjectShape;
/// # use std::convert::{Infallible, TryFrom};
/// #[derive(Debug, ObjectShape, PartialEq)]
/// struct CustomShape {
///     name: String,
///     width: i64,
/// }
///
/// let shape: Object = CustomShape {
///     name: "letter".to_string(),
///     width: 8,
/// }
/// .into();
///
/// assert_eq!(
///     shape,
///     object!("name" => "letter", "width" => 8),
/// );
///
/// let obj: Object = object!(
///     "name" => "letter",
///     "width" => 8,
/// );
///
/// assert_eq!(
///     CustomShape::try_from(obj),
///     Ok(CustomShape {
///         name: "letter".to_string(),
///         width: 8,
///     })
/// );
/// ```
///
/// # Renaming properties
///
/// By default, properties get the same name as the field in the struct. This can be changed with
/// the `field` attribute:
///
/// ```
/// # use qualia::{object, Object};
/// # use qualia_derive::ObjectShape;
/// # use std::convert::{Infallible, TryFrom};
/// #[derive(Debug, ObjectShape, PartialEq)]
/// struct CustomShape {
///     #[field("my-name")]
///     name: String,
///     width: i64,
/// }
///
/// let shape: Object = CustomShape {
///     name: "letter".to_string(),
///     width: 8,
/// }
/// .into();
///
/// assert_eq!(
///     shape,
///     object!("my-name" => "letter", "width" => 8),
/// );
/// ```
///
/// # Adding fixed properties
///
/// Additional fields with fixed values can be added with the `fixed_fields` attribute on
/// the struct:
///
/// ```
/// # use qualia::{object, Object};
/// # use qualia_derive::ObjectShape;
/// # use std::convert::{Infallible, TryFrom};
/// #[derive(Debug, ObjectShape, PartialEq)]
/// #[fixed_fields("kind" => "custom")]
/// struct CustomShape {
///     width: i64,
///     height: i64,
/// }
///
/// let shape: Object = CustomShape {
///     width: 8,
///     height: 11,
/// }
/// .into();
///
/// assert_eq!(
///     shape,
///     object!("kind" => "custom", "width" => 8, "height" => 11),
/// );
/// ```
///
/// There is a helper method provided, [`q()`](`qualia::ObjectShape::q()`), which makes use of
/// these fields. For example, for the above object shape, `CustomShape::q` returns a query for
/// `"kind" = "custom"`.
///
/// # Accessing other properties
///
/// To set and fetch unlisted properties, an [`Object`](qualia::Object) field with the
/// `rest_fields` attribute may be added.
///
/// ```
/// # use qualia::{object, Object};
/// # use qualia_derive::ObjectShape;
/// # use std::convert::{Infallible, TryFrom};
/// #[derive(Debug, ObjectShape, PartialEq)]
/// struct CustomShape {
///     width: i64,
///     #[rest_fields]
///     rest: Object,
/// }
///
/// let shape: Object = CustomShape {
///     width: 8,
///     rest: object!("height" => "tall"),
/// }
/// .into();
///
/// assert_eq!(
///     shape,
///     object!("width" => 8, "height" => "tall"),
/// );
/// ```
///
/// # Getting ID of inserted object
///
/// The ID of the object can be retrieved from an `Option<i64>` field named `object_id`:
///
/// ```
/// # use qualia::{object, Object};
/// # use qualia_derive::ObjectShape;
/// # use std::convert::{Infallible, TryFrom, TryInto};
/// #[derive(Debug, ObjectShape, PartialEq)]
/// struct CustomShape {
///     object_id: Option<i64>,
///     width: i64,
/// }
///
/// let shape: CustomShape = object!(
///     "object_id" => 42,
///     "width" => 65,
/// ).try_into().unwrap();
///
/// assert_eq!(
///     shape,
///     CustomShape { object_id: Some(42), width: 65 },
/// );
///
/// // let shape2 = CustomShape { object_id: None, width: 11 };
/// // store.insert_with_id(&mut shape2)?;
/// // assert!(shape2.object_id.is_some());
/// ```
///
/// # Accessing related objects
///
/// Often, objects contain references to other object's ID fields. If those objects have a defined
/// `ObjectShape`, then helper methods to fetch them can be generated with the `related`
/// attribute:
///
/// ```
/// # use qualia::{object, Object};
/// # use qualia_derive::ObjectShape;
/// # use std::convert::{Infallible, TryFrom};
/// #[derive(Debug, ObjectShape, PartialEq)]
/// struct ShapeGroup {
///     object_id: Option<i64>,
///     name: String,
/// }
///
/// #[derive(Debug, ObjectShape, PartialEq)]
/// struct CustomShape {
///     #[related(ShapeGroup)]
///     shape_group_id: i64,
///     width: i64,
/// }
///
/// // if let Some(group) = custom_shape.fetch_shape_group(&store)? {;
/// //     ...
/// ```
#[proc_macro_derive(ObjectShape, attributes(field, fixed_fields, rest_fields, related))]
pub fn derive_object_shape(input: TokenStream) -> TokenStream {
    let parsed_struct = parse_macro_input!(input as DeriveInput);
    let orig_type_name = parsed_struct.ident;

    let fixed_fields = try_or_error!(parse_fixed_fields(&parsed_struct.attrs));

    let mut fixed_field_names = Vec::new();
    let mut fixed_field_values = Vec::new();
    let mut fixed_field_accessors = Vec::new();

    for f in fixed_fields.into_iter() {
        fixed_field_names.push(f.name.clone());
        fixed_field_values.push(f.value.to_token_stream());
        fixed_field_accessors.push(f.accessor());
    }

    let struct_data = try_or_context!(
        match parsed_struct.data {
            syn::Data::Struct(s) => Ok(s),
            syn::Data::Enum(e) => Err(e.enum_token.span),
            syn::Data::Union(u) => Err(u.union_token.span),
        },
        "can only derive ObjectShape on a struct",
    );

    let named_fields = try_or_context!(
        match struct_data.fields {
            syn::Fields::Named(ref n) => Ok(n),
            syn::Fields::Unnamed(ref u) => Err(u.paren_token.span),
            syn::Fields::Unit => Err(struct_data.semi_token.unwrap().span),
        },
        "Can only derive ObjectType from a struct with named fields",
    );

    let (parsed_fields, rest_field_ident) = try_or_error!(parse_fields(&named_fields));

    let object_shape_with_id_impl =
        if let Some(field) = parsed_fields.iter().find(|f| f.name == "object_id") {
            let field_ident = field.ident.clone();

            quote!(
                impl qualia::ObjectShapeWithId for #orig_type_name {
                    fn get_object_id(&self) -> Option<i64> {
                        self.#field_ident
                    }

                    fn set_object_id(&mut self, object_id: i64) {
                        self.#field_ident = Some(object_id);
                    }
                }
            )
        } else {
            quote!()
        };

    let mut field_names = Vec::new();
    let mut field_idents = Vec::new();
    let mut field_accessors = Vec::new();
    let mut field_inserters = Vec::new();
    let mut field_related_impls = Vec::new();

    for f in parsed_fields.into_iter() {
        field_names.push(f.name);
        field_idents.push(f.ident);
        field_accessors.push(f.accessor);
        field_inserters.push(f.inserter);

        if let Some(related_impl) = f.related_impl {
            field_related_impls.push(related_impl);
        }
    }

    let rest_field_try_from = if let Some(ref rest_field_ident) = rest_field_ident {
        quote!(
            ,#rest_field_ident: object.into_iter().filter_map(|(k, v)| {
                if (#(k == #field_names)||*) {
                    None
                } else {
                    Some((k, v))
                }
            }).collect()
        )
    } else {
        quote!()
    };

    let rest_field_into = if let Some(ref rest_field_ident) = rest_field_ident {
        quote!(
            result.extend(self.#rest_field_ident.into_iter());
        )
    } else {
        quote!()
    };

    quote!(
        impl std::convert::TryFrom<qualia::Object> for #orig_type_name {
            type Error = qualia::ConversionError;

            fn try_from(object: qualia::Object) -> std::result::Result<#orig_type_name, qualia::ConversionError> {
                #(
                    {
                        let value = object.#fixed_field_accessors;

                        if value != #fixed_field_values {
                            return Err(
                                qualia::ConversionError::FixedFieldWrongValue(
                                    #fixed_field_names.to_string(),
                                    #fixed_field_values.into(),
                                    value.into(),
                                )
                            );
                        }
                    }
                )*

                Ok(#orig_type_name {
                    #(#field_idents: object.#field_accessors),*
                    #rest_field_try_from
                })
            }
        }

        impl std::convert::TryFrom<&qualia::Object> for #orig_type_name {
            type Error = qualia::ConversionError;

            fn try_from(orig_object: &qualia::Object) -> std::result::Result<#orig_type_name, qualia::ConversionError> {
                let object = orig_object.clone();
                #(
                    {
                        let value = object.#fixed_field_accessors;

                        if value != #fixed_field_values {
                            return Err(
                                qualia::ConversionError::FixedFieldWrongValue(
                                    #fixed_field_names.to_string(),
                                    #fixed_field_values.into(),
                                    value.into(),
                                )
                            );
                        }
                    }
                )*

                Ok(#orig_type_name {
                    #(#field_idents: object.#field_accessors),*
                    #rest_field_try_from
                })
            }
        }

        impl std::convert::Into<qualia::Object> for #orig_type_name {
            fn into(self) -> qualia::Object {
                use qualia::{object, Object};

                #[allow(unused_mut)]
                let mut result = object!(
                    #(#fixed_field_names => #fixed_field_values),*
                );
                #(#field_inserters)*
                #rest_field_into

                result
            }
        }

        impl qualia::ObjectShape for #orig_type_name {
            fn q() -> qualia::query_builder::QueryBuilder {
                qualia::Q
                #(
                    .equal(
                        #fixed_field_names,
                        #fixed_field_values,
                    )
                )*
            }
        }

        #object_shape_with_id_impl

        impl #orig_type_name {
            #(#field_related_impls)*
        }
    ).into()
}
