using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using System.Text;

namespace Visora.Editor.Services
{
    /// <summary>Small dependency-free JSON serializer for executor return values.</summary>
    internal static class VisoraJson
    {
        public static string Serialize(object value)
        {
            var builder = new StringBuilder();
            Append(builder, value);
            return builder.ToString();
        }

        private static void Append(StringBuilder builder, object value)
        {
            if (value == null) { builder.Append("null"); return; }
            if (value is string text) { AppendString(builder, text); return; }
            if (value is bool boolean) { builder.Append(boolean ? "true" : "false"); return; }
            if (value is char character) { AppendString(builder, character.ToString()); return; }
            if (value is Enum) { AppendString(builder, value.ToString()); return; }
            if (value is IFormattable number)
            {
                builder.Append(number.ToString(null, CultureInfo.InvariantCulture));
                return;
            }
            if (value is IDictionary dictionary) { AppendDictionary(builder, dictionary); return; }
            if (value is IEnumerable enumerable) { AppendEnumerable(builder, enumerable); return; }

            AppendObject(builder, value);
        }

        private static void AppendDictionary(StringBuilder builder, IDictionary dictionary)
        {
            builder.Append('{');
            var first = true;
            foreach (DictionaryEntry entry in dictionary)
            {
                if (!first) builder.Append(',');
                AppendString(builder, Convert.ToString(entry.Key, CultureInfo.InvariantCulture) ?? string.Empty);
                builder.Append(':');
                Append(builder, entry.Value);
                first = false;
            }
            builder.Append('}');
        }

        private static void AppendEnumerable(StringBuilder builder, IEnumerable values)
        {
            builder.Append('[');
            var first = true;
            foreach (var value in values)
            {
                if (!first) builder.Append(',');
                Append(builder, value);
                first = false;
            }
            builder.Append(']');
        }

        private static void AppendObject(StringBuilder builder, object value)
        {
            builder.Append('{');
            var first = true;
            foreach (var field in value.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public))
            {
                if (!first) builder.Append(',');
                AppendString(builder, field.Name);
                builder.Append(':');
                Append(builder, field.GetValue(value));
                first = false;
            }
            builder.Append('}');
        }

        private static void AppendString(StringBuilder builder, string value)
        {
            builder.Append('"');
            foreach (var character in value)
            {
                switch (character)
                {
                    case '\\': builder.Append("\\\\"); break;
                    case '"': builder.Append("\\\""); break;
                    case '\n': builder.Append("\\n"); break;
                    case '\r': builder.Append("\\r"); break;
                    case '\t': builder.Append("\\t"); break;
                    default:
                        if (character < ' ') builder.AppendFormat("\\u{0:x4}", (int)character);
                        else builder.Append(character);
                        break;
                }
            }
            builder.Append('"');
        }
    }
}
