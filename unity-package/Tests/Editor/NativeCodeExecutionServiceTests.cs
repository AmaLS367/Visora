using System.Collections.Generic;
using System.Threading.Tasks;
using NUnit.Framework;
using Visora.Editor.Services;

namespace Visora.Editor.Tests
{
    public class NativeCodeExecutionServiceTests
    {
        [Test]
        public async Task ExecutesLegacyStatementBodyAndReturnsStructuredResult()
        {
            var response = await NativeCodeExecutionService.ExecuteAsync(
                "return new Dictionary<string, object> { { \"answer\", 42 } };", 30f);

            Assert.That(response["success"], Is.EqualTo(true));
            var result = response["result"] as Dictionary<string, object>;
            Assert.That(result, Is.Not.Null);
            Assert.That(result["answer"], Is.EqualTo(42));
        }

        [Test]
        public async Task ReportsCompilerErrorsWithoutThrowingFromRouterContract()
        {
            var response = await NativeCodeExecutionService.ExecuteAsync("this is not valid C#;", 30f);

            Assert.That(response["success"], Is.EqualTo(false));
            Assert.That(response["error"], Is.EqualTo("Compilation failed"));
            Assert.That(response.ContainsKey("compilationErrors"), Is.True);
        }
    }
}
