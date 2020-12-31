extern crate proc_macro;
use proc_macro::TokenStream;
use quote::{quote, quote_spanned};
use syn::spanned::Spanned;
use syn::{parse_macro_input, DeriveInput};

macro_rules! try_or_context {
    ( $expr:expr, $message:expr$(,)? ) => {
        match $expr {
            Ok(x) => x,
            Err(span) => { return quote_spanned!(span=> compile_error!($message);).into() }
        }
    }
}

#[proc_macro_derive(ObjectShape)]
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

    let field_names_and_accessors: Vec<(_, _)> = try_or_context!(
        named_fields
            .named
            .iter()
            .map(|field| {
                let field_type = match &field.ty {
                    syn::Type::Path(p) => p,
                    _ => return Err(field.ty.span()),
                };

                let field_name = field.ident.clone().unwrap().to_string();

                let field_type_accessor = if field_type.path.is_ident("i64") {
                    quote!(
                        as_number()
                            .ok_or(
                                qualia::ConversionError::FieldWrongType(
                                    #field_name.to_string(),
                                    "number".to_string(),
                                ),
                            )?
                    )
                } else if field_type.path.is_ident("String") {
                    quote!(
                        as_str()
                            .ok_or(
                                qualia::ConversionError::FieldWrongType(
                                    #field_name.to_string(),
                                    "string".to_string(),
                                ),
                            )?
                            .clone()
                    )
                } else {
                    return Err(field_type.path.span());
                };

                Ok((field.ident.clone().unwrap(), field_type_accessor))
            })
            .collect(),
        "fields in ObjectShape must be i64 or String",
    );

    let (field_names, field_accessors): (Vec<_>, Vec<_>) =
        field_names_and_accessors.into_iter().unzip();

    let field_name_strings: Vec<_> = field_names
        .iter()
        .map(|field_name| field_name.to_string())
        .collect();

    let result = quote!(
        impl std::convert::TryFrom<qualia::Object> for #orig_type_name {
            type Error = qualia::ConversionError;

            fn try_from(object: qualia::Object) -> std::result::Result<#orig_type_name, qualia::ConversionError> {
                Ok(#orig_type_name {
                    #(
                        #field_names: object
                            .get(#field_name_strings)
                            .ok_or(qualia::ConversionError::FieldMissing(#field_name_strings.to_string()))?
                            .#field_accessors
                    ),*
                })
            }
        }

        impl std::convert::Into<qualia::Object> for #orig_type_name {
            fn into(self) -> qualia::Object {
                object!(
                    #(#field_name_strings => self.#field_names),*
                )
            }
        }

        impl qualia::ObjectShape for #orig_type_name {
            fn id(&self) -> i64 { todo!() }
        }
    );

    result.into()
}
