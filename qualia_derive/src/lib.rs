//! Derive macros for easily translating between objects in Qualia and Rust structs.

extern crate proc_macro;
use proc_macro::TokenStream;
use proc_macro2::TokenStream as TokenStream2;
use quote::{quote, quote_spanned, ToTokens};
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
        .find(|attr| attr.style == syn::AttrStyle::Outer && attr.path.is_ident("object_field"))
    {
        attr.parse_args::<syn::LitStr>().map(|lit| lit.value())
    } else {
        Ok(field.ident.clone().unwrap().to_string())
    }
}

struct ParsedField {
    ident: proc_macro2::Ident,
    name: String,
    accessor: TokenStream2,
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

fn parse_fields(named_fields: &syn::FieldsNamed) -> syn::Result<Vec<ParsedField>> {
    named_fields
        .named
        .iter()
        .map(|field| {
            let field_type = match &field.ty {
                syn::Type::Path(p) => p,
                _ => {
                    return Err(syn::Error::new_spanned(
                        &field.ty,
                        "fields in ObjectShape must be i64 or String",
                    ))
                }
            };

            let field_name = parse_field_name(&field)?;

            let field_type_accessor = if field_type.path.is_ident("i64") {
                Ok(number_accessor(&field_name))
            } else if field_type.path.is_ident("String") {
                Ok(string_accessor(&field_name))
            } else {
                Err(syn::Error::new_spanned(
                    &field_type.path,
                    "fields in ObjectShape must be i64 or String",
                ))
            }?;

            Ok(ParsedField {
                ident: field.ident.clone().unwrap(),
                name: field_name,
                accessor: field_type_accessor,
            })
        })
        .collect()
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
    let attr = match attrs.iter().find(|attr| {
        attr.style == syn::AttrStyle::Outer && attr.path.is_ident("object_fixed_fields")
    }) {
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
/// A basic example:
///
/// ```
/// # use qualia::{object, Object};
/// # use qualia_derive::ObjectShape;
/// # use std::convert::{Infallible, TryFrom};
/// #[derive(Debug, ObjectShape, PartialEq)]
/// struct CustomShape {
///     #[object_field("my-name")]
///     name: String,
///     width: i64,
///     height: i64,
/// }
///
/// let shape: Object = CustomShape {
///     name: "letter".to_string(),
///     width: 8,
///     height: 11,
/// }
/// .into();
///
/// assert_eq!(
///     shape,
///     object!("my-name" => "letter", "width" => 8, "height" => 11),
/// );
///
/// let obj: Object = object!(
///     "my-name" => "letter",
///     "width" => 8,
///     "height" => 11,
/// );
///
/// assert_eq!(
///     CustomShape::try_from(obj),
///     Ok(CustomShape {
///         name: "letter".to_string(),
///         width: 8,
///         height: 11,
///     })
/// );
/// ```
#[proc_macro_derive(ObjectShape, attributes(object_field, object_fixed_fields))]
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

    let parsed_fields = try_or_error!(parse_fields(&named_fields));

    let mut field_names = Vec::new();
    let mut field_idents = Vec::new();
    let mut field_accessors = Vec::new();

    for f in parsed_fields.into_iter() {
        field_names.push(f.name);
        field_idents.push(f.ident);
        field_accessors.push(f.accessor);
    }

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
                })
            }
        }

        impl std::convert::Into<qualia::Object> for #orig_type_name {
            fn into(self) -> qualia::Object {
                use qualia::{object, Object};

                object!(
                    #(#fixed_field_names => #fixed_field_values),*
                    #(#field_names => self.#field_idents),*
                )
            }
        }

        impl qualia::ObjectShape for #orig_type_name {}
    ).into()
}
