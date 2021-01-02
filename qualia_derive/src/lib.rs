extern crate proc_macro;
use proc_macro::TokenStream;
use quote::{quote, quote_spanned};
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
    accessor: syn::export::TokenStream2,
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

            let base_accessor = quote!(
                get(#field_name)
                .ok_or(qualia::ConversionError::FieldMissing(#field_name.to_string()))?
            );

            let field_type_accessor = if field_type.path.is_ident("i64") {
                Ok(quote!(
                    #base_accessor
                    .as_number()
                    .ok_or(
                        qualia::ConversionError::FieldWrongType(
                            #field_name.to_string(),
                            "number".to_string(),
                        ),
                    )?
                ))
            } else if field_type.path.is_ident("String") {
                Ok(quote!(
                    #base_accessor
                    .as_str()
                    .ok_or(
                        qualia::ConversionError::FieldWrongType(
                            #field_name.to_string(),
                            "string".to_string(),
                        ),
                    )?
                    .clone()
                ))
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

#[proc_macro_derive(ObjectShape, attributes(object_field))]
pub fn derive_object_shape(input: TokenStream) -> TokenStream {
    let parsed_struct = parse_macro_input!(input as DeriveInput);
    let orig_type_name = parsed_struct.ident;

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

    let parsed_fields = match parse_fields(&named_fields) {
        Ok(x) => x,
        Err(e) => return e.to_compile_error().into(),
    };

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
                Ok(#orig_type_name {
                    #(#field_idents: object.#field_accessors),*
                })
            }
        }

        impl std::convert::Into<qualia::Object> for #orig_type_name {
            fn into(self) -> qualia::Object {
                object!(
                    #(#field_names => self.#field_idents),*
                )
            }
        }

        impl qualia::ObjectShape for #orig_type_name {}
    ).into()
}
